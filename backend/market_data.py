"""Lightweight price source with CoinGecko and local simulation fallback."""
import asyncio
import time
import random
import httpx
from typing import Dict, List, Optional

# Local demo "universe" — maps to CoinGecko ids
UNIVERSE = [
    {"symbol": "BTC", "name": "Bitcoin", "cg_id": "bitcoin", "seed": 67324.50},
    {"symbol": "ETH", "name": "Ethereum", "cg_id": "ethereum", "seed": 3214.36},
    {"symbol": "SOL", "name": "Solana", "cg_id": "solana", "seed": 182.07},
    {"symbol": "BNB", "name": "BNB", "cg_id": "binancecoin", "seed": 598.21},
    {"symbol": "XRP", "name": "XRP", "cg_id": "ripple", "seed": 0.5423},
    {"symbol": "DOGE", "name": "Dogecoin", "cg_id": "dogecoin", "seed": 0.1587},
    {"symbol": "TRX", "name": "TRON", "cg_id": "tron", "seed": 0.1125},
    {"symbol": "AVAX", "name": "Avalanche", "cg_id": "avalanche-2", "seed": 36.18},
    {"symbol": "LINK", "name": "Chainlink", "cg_id": "chainlink", "seed": 14.26},
    {"symbol": "ADA", "name": "Cardano", "cg_id": "cardano", "seed": 0.4512},
    {"symbol": "MATIC", "name": "Polygon", "cg_id": "matic-network", "seed": 0.712},
    {"symbol": "DOT", "name": "Polkadot", "cg_id": "polkadot", "seed": 6.78},
]

STABLES = ["USDT"]

_cache: Dict[str, dict] = {}
_last_fetch = 0.0
_fetch_lock = asyncio.Lock()


def _seed_prices() -> Dict[str, dict]:
    """Fallback simulated prices when CoinGecko unreachable."""
    out = {}
    for c in UNIVERSE:
        change = random.uniform(-5, 7)
        price = c["seed"] * (1 + change / 100.0)
        out[c["symbol"]] = {
            "symbol": c["symbol"],
            "name": c["name"],
            "price": price,
            "change_24h": change,
            "volume_24h": random.uniform(1e7, 2e9),
            "market_cap": price * random.uniform(1e7, 1e10),
            "sparkline": [c["seed"] * (1 + random.uniform(-0.08, 0.08)) for _ in range(24)],
        }
    return out


async def _fetch_coingecko() -> Optional[Dict[str, dict]]:
    ids = ",".join(c["cg_id"] for c in UNIVERSE)
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&ids={ids}&order=market_cap_desc&sparkline=true"
        "&price_change_percentage=24h"
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
    except Exception:
        return None
    by_id = {c["cg_id"]: c for c in UNIVERSE}
    out = {}
    for item in data:
        meta = by_id.get(item.get("id"))
        if not meta:
            continue
        out[meta["symbol"]] = {
            "symbol": meta["symbol"],
            "name": meta["name"],
            "price": float(item.get("current_price") or meta["seed"]),
            "change_24h": float(item.get("price_change_percentage_24h") or 0),
            "volume_24h": float(item.get("total_volume") or 0),
            "market_cap": float(item.get("market_cap") or 0),
            "sparkline": (item.get("sparkline_in_7d") or {}).get("price", [])[-24:]
            or [meta["seed"]] * 24,
        }
    # Ensure all symbols present
    for meta in UNIVERSE:
        out.setdefault(meta["symbol"], None)
    return out


async def get_prices(force: bool = False) -> Dict[str, dict]:
    global _cache, _last_fetch
    now = time.time()
    if not force and _cache and (now - _last_fetch) < 30:
        return _cache
    async with _fetch_lock:
        if not force and _cache and (time.time() - _last_fetch) < 30:
            return _cache
        fresh = await _fetch_coingecko()
        if fresh is None:
            # fallback
            if not _cache:
                _cache = _seed_prices()
            else:
                # mild jitter
                for sym, row in _cache.items():
                    jitter = random.uniform(-0.004, 0.004)
                    row["price"] = max(0.00001, row["price"] * (1 + jitter))
        else:
            # merge, preserve prior for missing
            for sym, row in fresh.items():
                if row is not None:
                    _cache[sym] = row
            if not _cache:
                _cache = _seed_prices()
        _last_fetch = time.time()
        return _cache


async def get_price(symbol: str) -> float:
    data = await get_prices()
    row = data.get(symbol.upper())
    if not row:
        return 0.0
    return float(row["price"])


def generate_candles(base_price: float, count: int = 60, interval_sec: int = 60) -> List[dict]:
    """Deterministic-ish synthetic candles for a chart."""
    out = []
    now = int(time.time())
    price = base_price * 0.98
    for i in range(count):
        t = now - (count - i) * interval_sec
        drift = random.uniform(-0.004, 0.004)
        o = price
        c = max(0.00001, price * (1 + drift))
        hi = max(o, c) * (1 + random.uniform(0, 0.003))
        lo = min(o, c) * (1 - random.uniform(0, 0.003))
        vol = random.uniform(5, 120)
        out.append({"t": t, "o": round(o, 6), "h": round(hi, 6), "l": round(lo, 6), "c": round(c, 6), "v": round(vol, 2)})
        price = c
    return out


def generate_order_book(price: float, levels: int = 15) -> dict:
    bids = []
    asks = []
    for i in range(1, levels + 1):
        bid_p = price * (1 - 0.0005 * i - random.uniform(0, 0.0003))
        ask_p = price * (1 + 0.0005 * i + random.uniform(0, 0.0003))
        bids.append({"price": round(bid_p, 6), "qty": round(random.uniform(0.01, 3.5), 4)})
        asks.append({"price": round(ask_p, 6), "qty": round(random.uniform(0.01, 3.5), 4)})
    return {"bids": bids, "asks": asks}


def generate_recent_trades(price: float, count: int = 25) -> List[dict]:
    out = []
    now = int(time.time())
    for i in range(count):
        side = random.choice(["buy", "sell"])
        p = price * (1 + random.uniform(-0.001, 0.001))
        out.append({
            "t": now - i * random.randint(2, 20),
            "price": round(p, 6),
            "qty": round(random.uniform(0.001, 1.2), 4),
            "side": side,
        })
    return out

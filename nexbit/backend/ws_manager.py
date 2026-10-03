"""WebSocket broadcast manager for NEXBIT realtime market data."""
import asyncio
import json
import random
from typing import Dict, Set
from fastapi import WebSocket

from market_data import get_prices, generate_order_book, generate_recent_trades, UNIVERSE


class ConnectionManager:
    def __init__(self) -> None:
        # client -> set of channels
        self.clients: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients[ws] = set()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.pop(ws, None)

    async def subscribe(self, ws: WebSocket, channels) -> None:
        async with self._lock:
            if ws in self.clients:
                for ch in channels:
                    self.clients[ws].add(ch)

    async def unsubscribe(self, ws: WebSocket, channels) -> None:
        async with self._lock:
            if ws in self.clients:
                for ch in channels:
                    self.clients[ws].discard(ch)

    async def broadcast(self, channel: str, payload: dict) -> None:
        msg = json.dumps({"channel": channel, "data": payload})
        dead = []
        async with self._lock:
            targets = [ws for ws, chans in self.clients.items() if channel in chans]
        for ws in targets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self.clients.pop(ws, None)

    def active_channels(self) -> Set[str]:
        chs: Set[str] = set()
        for s in self.clients.values():
            chs |= s
        return chs


manager = ConnectionManager()


async def market_broadcaster() -> None:
    """Push tickers / orderbook / trades every ~1.5s to subscribers."""
    tick = 0
    while True:
        try:
            chs = manager.active_channels()
            # Always refresh prices (cached ~30s to CG, with jitter when stale)
            prices = await get_prices()

            if "tickers" in chs:
                items = []
                for sym, row in prices.items():
                    if not row:
                        continue
                    # Light jitter so prices visibly move between CG refreshes
                    jitter = random.uniform(-0.0008, 0.0008)
                    row["price"] = max(0.0001, row["price"] * (1 + jitter))
                    items.append({
                        "symbol": sym, "name": row["name"], "pair": f"{sym}/USDT",
                        "price": row["price"], "change_24h": row["change_24h"],
                        "volume_24h": row["volume_24h"], "market_cap": row["market_cap"],
                        "sparkline": row["sparkline"],
                    })
                items.sort(key=lambda x: -x["market_cap"])
                await manager.broadcast("tickers", {"items": items})

            # Per-symbol channels
            for ch in list(chs):
                if ch.startswith("ticker:"):
                    sym = ch.split(":", 1)[1].upper()
                    row = prices.get(sym)
                    if row:
                        await manager.broadcast(ch, {
                            "symbol": sym, "pair": f"{sym}/USDT",
                            "price": row["price"], "change_24h": row["change_24h"],
                            "volume_24h": row["volume_24h"],
                        })
                elif ch.startswith("orderbook:"):
                    sym = ch.split(":", 1)[1].upper()
                    row = prices.get(sym)
                    if row:
                        await manager.broadcast(ch, generate_order_book(row["price"], 15))
                elif ch.startswith("trades:"):
                    sym = ch.split(":", 1)[1].upper()
                    row = prices.get(sym)
                    if row and tick % 2 == 0:
                        # one new synthetic trade every ~3s
                        await manager.broadcast(ch, {
                            "trade": {
                                "t": int(asyncio.get_event_loop().time()),
                                "price": row["price"] * (1 + random.uniform(-0.0004, 0.0004)),
                                "qty": round(random.uniform(0.001, 0.9), 4),
                                "side": random.choice(["buy", "sell"]),
                            }
                        })
        except Exception:
            # swallow — this must never crash the task
            pass
        tick += 1
        await asyncio.sleep(1.5)

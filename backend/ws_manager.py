"""WebSocket broadcast manager for NEXBIT realtime market data."""
import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket

from market_data import get_prices, UNIVERSE
from db import db


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
                    pair = f"{sym}/USDT"
                    rows = await db.orders.find(
                        {"pair": pair, "status": {"$in": ["open", "partial"]}, "remaining_qty": {"$gt": 0}},
                        {"_id": 0, "side": 1, "price": 1, "remaining_qty": 1},
                    ).to_list(500)
                    levels = {"bids": {}, "asks": {}}
                    for order in rows:
                        price = float(order.get("price") or 0)
                        qty = float(order.get("remaining_qty") or 0)
                        if price <= 0 or qty <= 0:
                            continue
                        bucket = levels["bids"] if order.get("side") == "buy" else levels["asks"]
                        key = round(price, 8)
                        bucket[key] = bucket.get(key, 0.0) + qty
                    bids = [[p, q] for p, q in sorted(levels["bids"].items(), reverse=True)[:15]]
                    asks = [[p, q] for p, q in sorted(levels["asks"].items())[:15]]
                    await manager.broadcast(ch, {"bids": bids, "asks": asks})
                elif ch.startswith("trades:"):
                    sym = ch.split(":", 1)[1].upper()
                    pair = f"{sym}/USDT"
                    latest = await db.trades.find(
                        {"pair": pair},
                        {"_id": 0, "price": 1, "quantity": 1, "side": 1, "created_at": 1},
                    ).sort("created_at", -1).limit(1).to_list(1)
                    if latest:
                        trade = latest[0]
                        await manager.broadcast(ch, {
                            "trade": {
                                "t": trade.get("created_at"),
                                "price": float(trade.get("price") or 0),
                                "qty": float(trade.get("quantity") or 0),
                                "side": trade.get("side"),
                            }
                        })
        except Exception:
            # swallow — this must never crash the task
            pass
        tick += 1
        await asyncio.sleep(1.5)

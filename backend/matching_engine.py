"""Atomic spot matching engine for NEXBIT.

Orders match only against NEXBIT's own resting order book. No external price
feed is ever used to create a fill. Each match settles wallets, order state,
trade records and fee accounting in one MongoDB transaction.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from fastapi import HTTPException

from db import db, client
from financial import to_decimal, to_decimal128


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class MatchingEngine:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, pair: str) -> asyncio.Lock:
        return self._locks.setdefault(pair, asyncio.Lock())

    @staticmethod
    def _parse_pair(pair: str) -> tuple[str, str]:
        if "/" in pair:
            base, quote = pair.split("/", 1)
            return base.upper(), quote.upper()
        if pair.upper().endswith("USDT"):
            return pair[:-4].upper(), "USDT"
        raise HTTPException(400, "Invalid pair")

    async def place(self, data, user: dict) -> dict:
        pair = data.pair.upper()
        base, quote = self._parse_pair(pair)
        lock = self._lock(pair)

        async with lock:
            market = await db.market_pairs.find_one({"symbol": pair, "enabled": True}, {"_id": 0})
            if not market:
                raise HTTPException(404, "Market is disabled or does not exist")
            if to_decimal(data.quantity) < to_decimal(market.get("min_qty", 0)):
                raise HTTPException(400, "Quantity is below market minimum")
            if data.quantity <= 0:
                raise HTTPException(400, "Quantity must be positive")

            if data.type == "stop":
                raise HTTPException(400, "Stop orders require a trigger engine and are not enabled yet")

            if data.type == "limit":
                if data.price is None or data.price <= 0:
                    raise HTTPException(400, "Limit orders require a positive price")
            elif data.price is not None and data.price <= 0:
                raise HTTPException(400, "Price must be positive")

            maker_fee = to_decimal(market.get("maker_fee", "0.001"))
            taker_fee = to_decimal(market.get("taker_fee", "0.001"))
            if maker_fee < 0 or taker_fee < 0:
                raise HTTPException(500, "Invalid market fee configuration")

            candidates = await self._candidates(pair, data.side, data.type, data.price)
            plan = []
            remaining = to_decimal(data.quantity)
            required_quote = Decimal("0")

            for maker in candidates:
                maker_remaining = max(
                    Decimal("0"),
                    to_decimal(maker.get("quantity", 0)) - to_decimal(maker.get("filled_qty", 0)),
                )
                if maker_remaining <= 0:
                    continue
                fill_qty = min(remaining, maker_remaining)
                trade_price = to_decimal(maker["price"])
                notional = fill_qty * trade_price
                buyer_fee = notional * taker_fee if data.side == "buy" else notional * maker_fee
                if data.side == "buy":
                    required_quote += notional + buyer_fee
                plan.append((maker, fill_qty, trade_price, notional, buyer_fee))
                remaining -= fill_qty
                if remaining <= Decimal("0.000000000001"):
                    break

            if data.type == "market" and remaining > Decimal("0.000000000001"):
                raise HTTPException(400, "Insufficient liquidity in NEXBIT order book")

            if data.type == "limit":
                reserve_price = to_decimal(data.price)
                if data.side == "buy":
                    required_quote = to_decimal(data.quantity) * reserve_price * (Decimal("1") + taker_fee)
                else:
                    required_quote = to_decimal(data.quantity)

            if data.type == "market" and data.side == "sell":
                required_quote = Decimal("0")

            order_id = _new_id()
            created = _iso(_now())

            order = {
                "id": order_id,
                "user_id": user["id"],
                "pair": pair,
                "base": base,
                "quote": quote,
                "side": data.side,
                "type": data.type,
                "quantity": to_decimal128(data.quantity),
                "price": to_decimal128(data.price) if data.price is not None else None,
                "stop_price": None,
                "filled_qty": to_decimal128("0"),
                "remaining_qty": to_decimal128(data.quantity),
                "status": "open",
                "created_at": created,
                "updated_at": created,
            }

            async with await client.start_session() as session:
                async with session.start_transaction():
                    await db.orders.insert_one(order, session=session)
                    if data.side == "buy":
                        await self._move(user["id"], quote, "spot", -required_quote, session, order_id, "trade.order.reserve")
                        await self._move(user["id"], quote, "locked", required_quote, session, order_id, "trade.order.reserve")
                    else:
                        await self._move(user["id"], base, "spot", -to_decimal(data.quantity), session, order_id, "trade.order.reserve")
                        await self._move(user["id"], base, "locked", to_decimal(data.quantity), session, order_id, "trade.order.reserve")
                    filled = Decimal("0")
                    for maker, qty, trade_price, notional, buyer_fee in plan:
                        maker_id = maker["id"]
                        maker_user = maker["user_id"]
                        # The resting order is always maker; the incoming order
                        # is always taker. The fee asset is quote.
                        if data.side == "buy":
                            incoming_buyer_fee = notional * taker_fee
                            resting_fee = notional * maker_fee
                        else:
                            incoming_buyer_fee = notional * maker_fee
                            resting_fee = notional * taker_fee

                        buyer_id = user["id"] if data.side == "buy" else maker_user
                        seller_id = maker_user if data.side == "buy" else user["id"]

                        await self._move(
                            user_id=buyer_id, asset=quote, bucket="locked",
                            delta=-(notional + incoming_buyer_fee),
                            session=session, reference_id=maker_id,
                            reason="trade.fill",
                        )
                        await self._move(
                            user_id=buyer_id, asset=base, bucket="spot",
                            delta=qty, session=session, reference_id=maker_id,
                            reason="trade.fill",
                        )
                        # Buy orders reserve quote using the taker-fee ceiling.
                        # When a resting buy acts as maker, release the reserved
                        # fee spread immediately so locked funds cannot accumulate.
                        if data.side == "sell" and data.type in {"limit", "market"}:
                            reserved_fill = notional * (Decimal("1") + taker_fee)
                            actual_fill = notional + incoming_buyer_fee
                            release = max(Decimal("0"), reserved_fill - actual_fill)
                            if release > Decimal("0"):
                                await self._move(
                                    user_id=buyer_id, asset=quote, bucket="locked",
                                    delta=-release, session=session,
                                    reference_id=maker_id, reason="trade.maker_fee_release",
                                )
                                await self._move(
                                    user_id=buyer_id, asset=quote, bucket="spot",
                                    delta=release, session=session,
                                    reference_id=maker_id, reason="trade.maker_fee_release",
                                )
                        if data.side == "buy" and data.type == "limit":
                            reserved_fill = notional * (Decimal("1") + taker_fee)
                            actual_fill = notional + incoming_buyer_fee
                            release = max(Decimal("0"), reserved_fill - actual_fill)
                            if release > 0:
                                await self._move(
                                    user_id=buyer_id, asset=quote, bucket="locked",
                                    delta=-release, session=session,
                                    reference_id=order_id, reason="trade.price_improvement",
                                )
                                await self._move(
                                    user_id=buyer_id, asset=quote, bucket="spot",
                                    delta=release, session=session,
                                    reference_id=order_id, reason="trade.price_improvement",
                                )
                        await self._move(
                            user_id=seller_id, asset=base, bucket="locked",
                            delta=-qty, session=session, reference_id=order_id,
                            reason="trade.fill",
                        )
                        seller_fee = resting_fee
                        await self._move(
                            user_id=seller_id, asset=quote, bucket="spot",
                            delta=notional - seller_fee, session=session,
                            reference_id=order_id, reason="trade.fill",
                        )

                        total_fee = incoming_buyer_fee + seller_fee
                        treasury = os.environ.get("NEXBIT_FEE_TREASURY_USER_ID", "").strip()
                        if not treasury:
                            treasury_cfg = await db.config.find_one(
                                {"id": "fee_treasury"},
                                {"_id": 0, "user_id": 1},
                                session=session,
                            )
                            treasury = (treasury_cfg or {}).get("user_id", "").strip()
                        if not treasury and total_fee > 0:
                            raise HTTPException(503, "Fee treasury is not configured")
                        if total_fee > 0:
                            await self._move(
                                user_id=treasury, asset=quote, bucket="spot",
                                delta=total_fee, session=session,
                                reference_id=f"fee:{order_id}:{maker_id}",
                                reason="trade.fee",
                            )

                        await db.trades.insert_one({
                            "id": _new_id(),
                            "order_id": order_id,
                            "maker_order_id": maker_id,
                            "pair": pair,
                            "price": to_decimal128(trade_price),
                            "quantity": to_decimal128(qty),
                            "quote_amount": to_decimal128(notional),
                            "buyer_fee": to_decimal128(incoming_buyer_fee),
                            "seller_fee": to_decimal128(seller_fee),
                            "taker_user_id": user["id"],
                            "maker_user_id": maker_user,
                            "side": data.side,
                            "created_at": _iso(_now()),
                        }, session=session)

                        maker_new_filled = to_decimal(maker.get("filled_qty", 0)) + qty
                        maker_total = to_decimal(maker["quantity"])
                        maker_status = "filled" if maker_new_filled >= maker_total - Decimal("0.000000000001") else "partial"
                        await db.orders.update_one(
                            {"id": maker_id, "status": {"$in": ["open", "partial"]}},
                            {"$set": {
                                "filled_qty": maker_new_filled,
                                "remaining_qty": max(Decimal("0"), maker_total - maker_new_filled),
                                "status": maker_status,
                                "updated_at": _iso(_now()),
                            }},
                            session=session,
                        )
                        filled += qty

                    if filled > 0:
                        order["filled_qty"] = filled
                        order["remaining_qty"] = max(Decimal("0"), to_decimal(data.quantity) - filled)

                    if data.type == "market":
                        order["status"] = "filled" if order["remaining_qty"] <= Decimal("0.000000000001") else "cancelled"
                    elif order["remaining_qty"] <= Decimal("0.000000000001"):
                        order["status"] = "filled"
                    else:
                        order["status"] = "open" if filled == 0 else "partial"

                    await db.orders.update_one(
                        {"id": order_id},
                        {"$set": {
                            "filled_qty": order["filled_qty"],
                            "remaining_qty": order["remaining_qty"],
                            "status": order["status"],
                            "updated_at": _iso(_now()),
                        }},
                        session=session,
                    )

            return await db.orders.find_one({"id": order_id}, {"_id": 0})

    async def cancel(self, order_id: str, user: dict) -> dict:
        order = await db.orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
        if not order:
            raise HTTPException(404, "Order not found")
        pair = order["pair"].upper()
        async with self._lock(pair):
            order = await db.orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
            if not order or order.get("status") not in {"open", "partial"}:
                raise HTTPException(400, "Order not open")
            base, quote = self._parse_pair(pair)
            remaining = to_decimal(order.get("remaining_qty") or 0)
            if remaining <= 0:
                raise HTTPException(400, "Order has no remaining quantity")
            async with await client.start_session() as session:
                async with session.start_transaction():
                    if order["side"] == "buy":
                        market = await db.market_pairs.find_one({"symbol": pair}, {"_id": 0, "taker_fee": 1}, session=session)
                        fee = to_decimal((market or {}).get("taker_fee", "0.001"))
                        release = remaining * to_decimal(order["price"]) * (Decimal("1") + fee)
                        await self._move(user["id"], quote, "locked", -release, session, order_id, "trade.order.cancel")
                        await self._move(user["id"], quote, "spot", release, session, order_id, "trade.order.cancel")
                    else:
                        await self._move(user["id"], base, "locked", -remaining, session, order_id, "trade.order.cancel")
                        await self._move(user["id"], base, "spot", remaining, session, order_id, "trade.order.cancel")
                    await db.orders.update_one(
                        {"id": order_id, "user_id": user["id"], "status": {"$in": ["open", "partial"]}},
                        {"$set": {
                            "status": "cancelled",
                            "remaining_qty": to_decimal128("0"),
                            "cancelled_at": _iso(_now()),
                            "updated_at": _iso(_now()),
                        }},
                        session=session,
                    )
            return await db.orders.find_one({"id": order_id}, {"_id": 0})

    async def _candidates(self, pair: str, side: str, order_type: str, price: Decimal | None) -> list[dict]:
        opposite = "sell" if side == "buy" else "buy"
        rows = await db.orders.find(
            {"pair": pair, "side": opposite, "status": {"$in": ["open", "partial"]}, "type": "limit"},
            {"_id": 0},
        ).sort([("price", 1 if side == "buy" else -1), ("created_at", 1)]).limit(500).to_list(500)
        if order_type != "limit":
            return rows
        if side == "buy":
            return [r for r in rows if to_decimal(r["price"]) <= to_decimal(price)]
        return [r for r in rows if to_decimal(r["price"]) >= to_decimal(price)]

    async def _move(self, user_id, asset, bucket, delta, session, reference_id, reason):
        delta = to_decimal(delta)
        if delta == 0:
            return
        query = {"user_id": user_id, "asset": asset}
        if delta < 0:
            query[bucket] = {"$gte": to_decimal128(-delta)}
        result = await db.wallets.update_one(
            query,
            {"$inc": {bucket: to_decimal128(delta)}, "$set": {"updated_at": _iso(_now())}},
            session=session,
        )
        if result.matched_count != 1:
            raise HTTPException(400, f"Insufficient {asset} in {bucket}")
        wallet = await db.wallets.find_one({"user_id": user_id, "asset": asset}, {"_id": 0}, session=session)
        await db.ledger_entries.insert_one({
            "id": _new_id(),
            "user_id": user_id,
            "asset": asset,
            "bucket": bucket,
            "delta": to_decimal128(delta),
            "balance_after": wallet.get(bucket) or to_decimal128("0"),
            "reason": reason,
            "reference_id": reference_id,
            "created_at": _iso(_now()),
        }, session=session)


class _DistributedPairLock:
    """Mongo-backed lease lock shared by all API instances for one pair."""

    def __init__(self, pair: str, lease_seconds: int = 60) -> None:
        self.pair = pair
        self.lease_seconds = lease_seconds
        self.owner = _new_id()

    async def __aenter__(self):
        deadline = _now() + timedelta(seconds=15)
        while True:
            now = _now()
            if now >= deadline:
                raise HTTPException(503, "Matching engine is busy; please retry")
            try:
                result = await db.matching_locks.find_one_and_update(
                    {"key": f"pair:{self.pair}", "$or": [{"expires_at": {"$lte": now}}, {"owner": self.owner}]},
                    {"$set": {"owner": self.owner, "expires_at": now + timedelta(seconds=self.lease_seconds), "updated_at": now}},
                    upsert=True,
                    return_document=True,
                )
                if result and result.get("owner") == self.owner:
                    return self
            except Exception as exc:
                if exc.__class__.__name__ != "DuplicateKeyError":
                    raise
            await asyncio.sleep(0.05)

    async def __aexit__(self, exc_type, exc, tb):
        await db.matching_locks.delete_one({"key": f"pair:{self.pair}", "owner": self.owner})


matching_engine = MatchingEngine()

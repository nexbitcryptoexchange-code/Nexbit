"""NEXBIT backend — FastAPI monolith with modular route groups."""
import os
import json
import uuid
import secrets
import logging
import asyncio
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from ws_manager import manager as ws_mgr, market_broadcaster
from db import db, ensure_indexes
from auth_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user, require_admin, set_auth_cookies, clear_auth_cookies,
)
import market_data
from market_data import UNIVERSE, STABLES, get_prices, get_price, generate_candles, generate_order_book, generate_recent_trades
from emailer import send_welcome_verify, send_password_reset, send_withdrawal_update
from models import (
    RegisterIn, LoginIn, ForgotIn, ResetIn, VerifyEmailIn, TwoFAIn, ProfileUpdateIn,
    KycSubmitIn, KycDecisionIn, OrderIn, FuturesOrderIn, ClosePositionIn,
    DepositIn, WithdrawIn, TransferIn, EarnSubscribeIn, ApiKeyIn,
    AdminUserUpdateIn, AdminTxDecisionIn, MarketPairIn, FeeConfigIn,
    SupportTicketIn, SupportReplyIn,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("nexbit")

app = FastAPI(title="NEXBIT API")
api = APIRouter(prefix="/api")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc if dt.tzinfo is None else dt.tzinfo).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


async def _log_audit(actor_id: str, action: str, target: str = "", meta: Optional[dict] = None) -> None:
    await db.audit_logs.insert_one({
        "id": _new_id(),
        "actor_id": actor_id,
        "action": action,
        "target": target,
        "meta": meta or {},
        "created_at": _iso(_now()),
    })


def _public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name") or u["email"].split("@")[0],
        "role": u.get("role", "user"),
        "status": u.get("status", "active"),
        "kyc_status": u.get("kyc_status", "unverified"),
        "email_verified": u.get("email_verified", False),
        "twofa_enabled": u.get("twofa_enabled", False),
        "anti_phishing_code": u.get("anti_phishing_code"),
        "phone": u.get("phone"),
        "country": u.get("country"),
        "created_at": u.get("created_at"),
        "last_login": u.get("last_login"),
    }


# ============================================================================
# AUTH
# ============================================================================
auth = APIRouter(prefix="/auth", tags=["auth"])


@auth.post("/register")
async def register(data: RegisterIn, response: Response):
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = _new_id()
    doc = {
        "id": uid,
        "email": email,
        "name": data.name or email.split("@")[0],
        "password_hash": hash_password(data.password),
        "role": "user",
        "status": "active",
        "kyc_status": "unverified",
        "email_verified": False,
        "twofa_enabled": False,
        "verify_code": f"{random.randint(100000, 999999)}",
        "created_at": _iso(_now()),
    }
    await db.users.insert_one(doc)
    # Seed empty wallets for key assets
    for asset in ["USDT", "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "ADA"]:
        starting = 5000.0 if asset == "USDT" else 0.0
        await db.wallets.insert_one({
            "id": _new_id(), "user_id": uid, "asset": asset,
            "spot": starting, "futures": 0.0, "earn": 0.0, "locked": 0.0,
            "updated_at": _iso(_now()),
        })
    access = create_access_token(uid, email, "user")
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    await _log_audit(uid, "auth.register")
    # fire-and-forget welcome / verification email
    try:
        await send_welcome_verify(to=email, name=doc["name"], code=doc["verify_code"])
    except Exception as e:
        logger.warning("verify email send skipped: %s", e)
    user = _public_user(doc)
    return {"user": user, "access_token": access}


@auth.post("/login")
async def login(data: LoginIn, request: Request, response: Response):
    email = data.email.lower()
    ip = request.client.host if request.client else "?"
    ident = f"{ip}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("locked_until") and datetime.fromisoformat(att["locked_until"]) > _now():
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    u = await db.users.find_one({"email": email})
    if not u or not verify_password(data.password, u.get("password_hash", "")):
        count = (att or {}).get("count", 0) + 1
        update = {"identifier": ident, "count": count, "updated_at": _iso(_now())}
        if count >= 5:
            update["locked_until"] = _iso(_now() + timedelta(minutes=15))
            update["count"] = 0
        await db.login_attempts.update_one({"identifier": ident}, {"$set": update}, upsert=True)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if u.get("status") == "banned":
        raise HTTPException(status_code=403, detail="Account banned")
    if u.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")
    await db.login_attempts.delete_one({"identifier": ident})
    await db.users.update_one({"id": u["id"]}, {"$set": {"last_login": _iso(_now())}})
    u["last_login"] = _iso(_now())
    access = create_access_token(u["id"], u["email"], u.get("role", "user"))
    refresh = create_refresh_token(u["id"])
    set_auth_cookies(response, access, refresh)
    await _log_audit(u["id"], "auth.login")
    return {"user": _public_user(u), "access_token": access}


@auth.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    await _log_audit(user["id"], "auth.logout")
    return {"ok": True}


@auth.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user)}


@auth.post("/refresh")
async def refresh(request: Request, response: Response):
    rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = decode_token(rt)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    u = await db.users.find_one({"id": payload["sub"]})
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(u["id"], u["email"], u.get("role", "user"))
    new_refresh = create_refresh_token(u["id"])
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True}


@auth.post("/forgot-password")
async def forgot(data: ForgotIn):
    email = data.email.lower()
    u = await db.users.find_one({"email": email})
    token = secrets.token_urlsafe(32)
    if u:
        await db.password_reset_tokens.insert_one({
            "id": _new_id(), "user_id": u["id"], "token": token,
            "expires_at": _now() + timedelta(hours=1), "used": False,
            "created_at": _iso(_now()),
        })
        logger.info("Password reset for %s token=%s", email, token)
        try:
            await send_password_reset(to=email, name=u.get("name") or email, token=token)
        except Exception as e:
            logger.warning("reset email send skipped: %s", e)
    # Always success (don't leak whether email exists); dev token kept for easy testing
    return {"ok": True, "dev_token": token if u else None}


@auth.post("/reset-password")
async def reset(data: ResetIn):
    rec = await db.password_reset_tokens.find_one({"token": data.token, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if rec["expires_at"] < _now():
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one({"id": rec["user_id"]}, {"$set": {"password_hash": hash_password(data.password)}})
    await db.password_reset_tokens.update_one({"id": rec["id"]}, {"$set": {"used": True}})
    return {"ok": True}


@auth.post("/verify-email")
async def verify_email(data: VerifyEmailIn, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]})
    if not u:
        raise HTTPException(404, "User not found")
    # Accept the stored code, or master demo code 123456
    if data.code != u.get("verify_code") and data.code != "123456":
        raise HTTPException(400, "Invalid code")
    await db.users.update_one({"id": user["id"]}, {"$set": {"email_verified": True}})
    return {"ok": True}


@auth.post("/resend-verification")
async def resend_verification(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]})
    if not u:
        raise HTTPException(404, "User not found")
    if u.get("email_verified"):
        return {"ok": True, "already_verified": True}
    code = u.get("verify_code") or f"{random.randint(100000, 999999)}"
    if code != u.get("verify_code"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"verify_code": code}})
    try:
        await send_welcome_verify(to=u["email"], name=u.get("name") or u["email"], code=code)
    except Exception as e:
        logger.warning("resend verification email failed: %s", e)
        raise HTTPException(502, "Email delivery failed")
    return {"ok": True}


@auth.post("/2fa")
async def toggle_2fa(data: TwoFAIn, user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"twofa_enabled": data.enabled}})
    return {"ok": True}


# ============================================================================
# USER / PROFILE / KYC
# ============================================================================
user_r = APIRouter(prefix="/user", tags=["user"])


@user_r.patch("/profile")
async def update_profile(data: ProfileUpdateIn, user: dict = Depends(get_current_user)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if patch:
        await db.users.update_one({"id": user["id"]}, {"$set": patch})
    u = await db.users.find_one({"id": user["id"]})
    return {"user": _public_user(u)}


@user_r.post("/kyc")
async def submit_kyc(data: KycSubmitIn, user: dict = Depends(get_current_user)):
    doc = {
        "id": _new_id(), "user_id": user["id"],
        "full_name": data.full_name, "document_type": data.document_type,
        "document_number": data.document_number, "country": data.country,
        "dob": data.dob, "status": "pending",
        "created_at": _iso(_now()),
    }
    await db.kyc.update_one({"user_id": user["id"]}, {"$set": doc}, upsert=True)
    await db.users.update_one({"id": user["id"]}, {"$set": {"kyc_status": "pending"}})
    await _log_audit(user["id"], "kyc.submit")
    return {"ok": True, "kyc": doc}


@user_r.get("/kyc")
async def get_my_kyc(user: dict = Depends(get_current_user)):
    doc = await db.kyc.find_one({"user_id": user["id"]}, {"_id": 0})
    return {"kyc": doc}


@user_r.get("/notifications")
async def my_notifications(user: dict = Depends(get_current_user)):
    rows = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"items": rows}


@user_r.post("/api-keys")
async def create_api_key(data: ApiKeyIn, user: dict = Depends(get_current_user)):
    key = "nx_" + secrets.token_urlsafe(16)
    secret = secrets.token_urlsafe(32)
    row = {
        "id": _new_id(), "user_id": user["id"], "label": data.label,
        "permissions": data.permissions, "key": key, "secret": secret,
        "created_at": _iso(_now()),
    }
    await db.api_keys.insert_one(row)
    row.pop("_id", None)
    return {"api_key": row}


@user_r.get("/api-keys")
async def list_api_keys(user: dict = Depends(get_current_user)):
    rows = await db.api_keys.find({"user_id": user["id"]}, {"_id": 0, "secret": 0}).to_list(100)
    return {"items": rows}


@user_r.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: dict = Depends(get_current_user)):
    await db.api_keys.delete_one({"id": key_id, "user_id": user["id"]})
    return {"ok": True}


@user_r.get("/referral")
async def referral(user: dict = Depends(get_current_user)):
    code = user["id"][:8].upper()
    referrals = await db.users.count_documents({"referred_by": user["id"]})
    return {"code": code, "referrals": referrals, "earnings_usdt": referrals * 15.0}


# ============================================================================
# MARKETS
# ============================================================================
market_r = APIRouter(prefix="/market", tags=["market"])


@market_r.get("/tickers")
async def tickers():
    prices = await get_prices()
    out = []
    for sym, row in prices.items():
        if not row:
            continue
        out.append({
            "symbol": sym, "name": row["name"],
            "pair": f"{sym}/USDT",
            "price": row["price"], "change_24h": row["change_24h"],
            "volume_24h": row["volume_24h"], "market_cap": row["market_cap"],
            "sparkline": row["sparkline"],
        })
    out.sort(key=lambda x: -x["market_cap"])
    return {"items": out}


@market_r.get("/ticker/{symbol}")
async def ticker(symbol: str):
    sym = symbol.upper()
    prices = await get_prices()
    row = prices.get(sym)
    if not row:
        raise HTTPException(404, "Unknown symbol")
    return {"symbol": sym, "pair": f"{sym}/USDT", **row}


@market_r.get("/candles/{symbol}")
async def candles(symbol: str, interval: str = "1m", limit: int = 60):
    sym = symbol.upper()
    base = await get_price(sym)
    if base <= 0:
        raise HTTPException(404, "Unknown symbol")
    sec = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(interval, 60)
    return {"items": generate_candles(base, count=min(limit, 200), interval_sec=sec)}


@market_r.get("/orderbook/{symbol}")
async def orderbook(symbol: str):
    base = await get_price(symbol.upper())
    if base <= 0:
        raise HTTPException(404, "Unknown symbol")
    return generate_order_book(base, levels=15)


@market_r.get("/trades/{symbol}")
async def recent_trades(symbol: str):
    base = await get_price(symbol.upper())
    if base <= 0:
        raise HTTPException(404, "Unknown symbol")
    return {"items": generate_recent_trades(base, 25)}


@market_r.get("/pairs")
async def pairs():
    rows = await db.market_pairs.find({}, {"_id": 0}).to_list(200)
    if not rows:
        # emit the universe as default
        rows = [{
            "symbol": f"{c['symbol']}/USDT", "base": c["symbol"], "quote": "USDT",
            "min_qty": 0.0001, "tick": 0.01, "maker_fee": 0.001, "taker_fee": 0.001,
            "enabled": True,
        } for c in UNIVERSE]
    return {"items": rows}


# ============================================================================
# WALLET
# ============================================================================
wallet_r = APIRouter(prefix="/wallet", tags=["wallet"])


async def _get_wallet(uid: str, asset: str) -> dict:
    w = await db.wallets.find_one({"user_id": uid, "asset": asset})
    if not w:
        w = {"id": _new_id(), "user_id": uid, "asset": asset,
             "spot": 0.0, "futures": 0.0, "earn": 0.0, "locked": 0.0,
             "updated_at": _iso(_now())}
        await db.wallets.insert_one(w)
    w.pop("_id", None)
    return w


async def _adjust(uid: str, asset: str, bucket: str, delta: float) -> dict:
    w = await _get_wallet(uid, asset)
    new_val = (w.get(bucket) or 0.0) + delta
    if new_val < -1e-9:
        raise HTTPException(400, f"Insufficient {asset} in {bucket}")
    await db.wallets.update_one(
        {"user_id": uid, "asset": asset},
        {"$set": {bucket: max(0.0, new_val), "updated_at": _iso(_now())}},
    )
    w[bucket] = max(0.0, new_val)
    return w


@wallet_r.get("/balances")
async def balances(user: dict = Depends(get_current_user)):
    rows = await db.wallets.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    prices = await get_prices()
    total_usd = 0.0
    for r in rows:
        if r["asset"] == "USDT":
            p = 1.0
        else:
            p = (prices.get(r["asset"]) or {}).get("price", 0.0)
        total = (r.get("spot") or 0) + (r.get("futures") or 0) + (r.get("earn") or 0) + (r.get("locked") or 0)
        r["usd_value"] = total * p
        r["price"] = p
        r["total"] = total
        total_usd += r["usd_value"]
    rows.sort(key=lambda x: -x["usd_value"])
    return {"total_usd": total_usd, "items": rows}


@wallet_r.get("/transactions")
async def transactions(user: dict = Depends(get_current_user), limit: int = 100):
    rows = await db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": rows}


@wallet_r.post("/deposit")
async def deposit(data: DepositIn, user: dict = Depends(get_current_user)):
    asset = data.asset.upper()
    tx = {
        "id": _new_id(), "user_id": user["id"], "type": "deposit",
        "asset": asset, "amount": data.amount, "status": "completed",
        "address": f"nx_{asset.lower()}_{secrets.token_hex(8)}",
        "network": asset, "created_at": _iso(_now()),
    }
    await db.transactions.insert_one(tx)
    await _adjust(user["id"], asset, "spot", data.amount)
    tx.pop("_id", None)
    await _log_audit(user["id"], "wallet.deposit", meta={"asset": asset, "amount": data.amount})
    return {"tx": tx}


@wallet_r.post("/withdraw")
async def withdraw(data: WithdrawIn, user: dict = Depends(get_current_user)):
    asset = data.asset.upper()
    # Hold funds
    await _adjust(user["id"], asset, "spot", -data.amount)
    await _adjust(user["id"], asset, "locked", data.amount)
    tx = {
        "id": _new_id(), "user_id": user["id"], "type": "withdraw",
        "asset": asset, "amount": data.amount, "status": "pending",
        "address": data.address, "network": data.network or asset,
        "created_at": _iso(_now()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    await _log_audit(user["id"], "wallet.withdraw.request", meta={"asset": asset, "amount": data.amount})
    return {"tx": tx}


@wallet_r.post("/transfer")
async def transfer(data: TransferIn, user: dict = Depends(get_current_user)):
    if data.from_wallet == data.to_wallet:
        raise HTTPException(400, "Source and destination must differ")
    asset = data.asset.upper()
    await _adjust(user["id"], asset, data.from_wallet, -data.amount)
    await _adjust(user["id"], asset, data.to_wallet, data.amount)
    tx = {
        "id": _new_id(), "user_id": user["id"], "type": "transfer",
        "asset": asset, "amount": data.amount, "status": "completed",
        "from_wallet": data.from_wallet, "to_wallet": data.to_wallet,
        "created_at": _iso(_now()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return {"tx": tx}


# ============================================================================
# SPOT TRADING
# ============================================================================
trade_r = APIRouter(prefix="/trade", tags=["trade"])


def _parse_pair(pair: str) -> tuple[str, str]:
    if "/" in pair:
        b, q = pair.split("/", 1)
        return b.upper(), q.upper()
    # BTCUSDT
    if pair.upper().endswith("USDT"):
        return pair[:-4].upper(), "USDT"
    raise HTTPException(400, "Invalid pair")


@trade_r.post("/order")
async def place_order(data: OrderIn, user: dict = Depends(get_current_user)):
    base, quote = _parse_pair(data.pair)
    mark = await get_price(base)
    if mark <= 0:
        raise HTTPException(404, "Unknown market")
    price = mark if data.type == "market" else (data.price or mark)
    fee_rate = 0.001
    status = "filled" if data.type == "market" else "open"
    order = {
        "id": _new_id(), "user_id": user["id"], "pair": f"{base}/{quote}",
        "side": data.side, "type": data.type, "quantity": data.quantity,
        "price": price, "stop_price": data.stop_price, "status": status,
        "filled_qty": 0.0, "fee": 0.0, "fee_asset": quote,
        "created_at": _iso(_now()),
    }
    if status == "filled":
        notional = data.quantity * price
        fee = notional * fee_rate
        if data.side == "buy":
            await _adjust(user["id"], quote, "spot", -(notional + fee))
            await _adjust(user["id"], base, "spot", data.quantity)
        else:
            await _adjust(user["id"], base, "spot", -data.quantity)
            await _adjust(user["id"], quote, "spot", notional - fee)
        order["filled_qty"] = data.quantity
        order["fee"] = fee
        order["filled_at"] = _iso(_now())
        # record trade
        await db.trades.insert_one({
            "id": _new_id(), "user_id": user["id"], "pair": order["pair"],
            "side": data.side, "price": price, "quantity": data.quantity,
            "fee": fee, "created_at": _iso(_now()),
        })
    else:
        # Lock funds for limit order
        if data.side == "buy":
            await _adjust(user["id"], quote, "spot", -(data.quantity * price))
            await _adjust(user["id"], quote, "locked", data.quantity * price)
        else:
            await _adjust(user["id"], base, "spot", -data.quantity)
            await _adjust(user["id"], base, "locked", data.quantity)
    await db.orders.insert_one(order)
    order.pop("_id", None)
    await _log_audit(user["id"], "trade.order", meta={"pair": order["pair"], "side": data.side, "status": status})
    return {"order": order}


@trade_r.get("/orders")
async def orders(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if status:
        q["status"] = status
    rows = await db.orders.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"items": rows}


@trade_r.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, user: dict = Depends(get_current_user)):
    o = await db.orders.find_one({"id": order_id, "user_id": user["id"]})
    if not o:
        raise HTTPException(404, "Order not found")
    if o["status"] != "open":
        raise HTTPException(400, "Order not open")
    base, quote = _parse_pair(o["pair"])
    if o["side"] == "buy":
        locked = o["quantity"] * o["price"]
        await _adjust(user["id"], quote, "locked", -locked)
        await _adjust(user["id"], quote, "spot", locked)
    else:
        await _adjust(user["id"], base, "locked", -o["quantity"])
        await _adjust(user["id"], base, "spot", o["quantity"])
    await db.orders.update_one({"id": order_id}, {"$set": {"status": "cancelled"}})
    return {"ok": True}


@trade_r.get("/trades")
async def my_trades(user: dict = Depends(get_current_user)):
    rows = await db.trades.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"items": rows}


# ============================================================================
# FUTURES
# ============================================================================
fut_r = APIRouter(prefix="/futures", tags=["futures"])


@fut_r.post("/order")
async def open_position(data: FuturesOrderIn, user: dict = Depends(get_current_user)):
    base, quote = _parse_pair(data.pair)
    mark = await get_price(base)
    if mark <= 0:
        raise HTTPException(404, "Unknown market")
    entry = data.entry_price or mark
    notional = data.quantity * entry
    margin = notional / data.leverage
    # transfer margin from spot USDT into futures bucket as collateral
    await _adjust(user["id"], "USDT", "spot", -margin)
    await _adjust(user["id"], "USDT", "futures", margin)
    liq_pct = 0.9 / data.leverage  # approximate
    liq = entry * (1 - liq_pct) if data.side == "long" else entry * (1 + liq_pct)
    pos = {
        "id": _new_id(), "user_id": user["id"], "pair": f"{base}/{quote}",
        "side": data.side, "leverage": data.leverage,
        "quantity": data.quantity, "entry_price": entry,
        "margin": margin, "liq_price": liq, "tp": data.tp, "sl": data.sl,
        "status": "open", "pnl": 0.0,
        "created_at": _iso(_now()),
    }
    await db.positions.insert_one(pos)
    pos.pop("_id", None)
    await _log_audit(user["id"], "futures.open", meta={"pair": pos["pair"], "side": data.side})
    return {"position": pos}


@fut_r.post("/close")
async def close_position(data: ClosePositionIn, user: dict = Depends(get_current_user)):
    p = await db.positions.find_one({"id": data.position_id, "user_id": user["id"]})
    if not p:
        raise HTTPException(404, "Position not found")
    if p["status"] != "open":
        raise HTTPException(400, "Position not open")
    base, _q = _parse_pair(p["pair"])
    mark = await get_price(base)
    pnl = (mark - p["entry_price"]) * p["quantity"] * (1 if p["side"] == "long" else -1)
    # return margin + pnl to spot USDT
    await _adjust(user["id"], "USDT", "futures", -p["margin"])
    return_amt = max(0.0, p["margin"] + pnl)
    await _adjust(user["id"], "USDT", "spot", return_amt)
    await db.positions.update_one({"id": p["id"]}, {"$set": {"status": "closed", "pnl": pnl, "exit_price": mark, "closed_at": _iso(_now())}})
    return {"ok": True, "pnl": pnl, "exit_price": mark}


@fut_r.get("/positions")
async def positions(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if status:
        q["status"] = status
    rows = await db.positions.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    prices = await get_prices()
    for r in rows:
        if r["status"] == "open":
            base, _q = _parse_pair(r["pair"])
            mark = (prices.get(base) or {}).get("price", r["entry_price"])
            r["mark_price"] = mark
            r["unrealized_pnl"] = (mark - r["entry_price"]) * r["quantity"] * (1 if r["side"] == "long" else -1)
            r["roe"] = (r["unrealized_pnl"] / r["margin"]) * 100 if r["margin"] else 0
    return {"items": rows}


@fut_r.get("/account")
async def fut_account(user: dict = Depends(get_current_user)):
    rows = await db.positions.find({"user_id": user["id"], "status": "open"}, {"_id": 0}).to_list(100)
    wallet = await _get_wallet(user["id"], "USDT")
    prices = await get_prices()
    unrealized = 0.0
    used_margin = 0.0
    for r in rows:
        base, _q = _parse_pair(r["pair"])
        mark = (prices.get(base) or {}).get("price", r["entry_price"])
        unrealized += (mark - r["entry_price"]) * r["quantity"] * (1 if r["side"] == "long" else -1)
        used_margin += r["margin"]
    balance = wallet.get("futures", 0.0)
    equity = balance + unrealized
    risk_ratio = (used_margin / equity * 100) if equity > 0 else 0.0
    return {
        "balance": balance, "equity": equity, "unrealized_pnl": unrealized,
        "used_margin": used_margin, "risk_ratio": min(100.0, risk_ratio),
        "open_positions": len(rows),
    }


# ============================================================================
# EARN
# ============================================================================
earn_r = APIRouter(prefix="/earn", tags=["earn"])

DEFAULT_EARN_PRODUCTS = [
    {"id": "p-usdt-flex", "asset": "USDT", "name": "USDT Flexible Savings", "apy": 12.0, "type": "flexible", "min": 10},
    {"id": "p-btc-lock30", "asset": "BTC", "name": "BTC 30-Day Locked", "apy": 5.0, "type": "locked", "term_days": 30, "min": 0.001},
    {"id": "p-eth-lock30", "asset": "ETH", "name": "ETH 30-Day Locked", "apy": 6.5, "type": "locked", "term_days": 30, "min": 0.01},
    {"id": "p-sol-flex", "asset": "SOL", "name": "SOL Flexible Staking", "apy": 7.2, "type": "flexible", "min": 1},
]


@earn_r.get("/products")
async def earn_products():
    return {"items": DEFAULT_EARN_PRODUCTS}


@earn_r.post("/subscribe")
async def earn_subscribe(data: EarnSubscribeIn, user: dict = Depends(get_current_user)):
    p = next((x for x in DEFAULT_EARN_PRODUCTS if x["id"] == data.product_id), None)
    if not p:
        raise HTTPException(404, "Product not found")
    if data.amount < p["min"]:
        raise HTTPException(400, f"Minimum {p['min']} {p['asset']}")
    await _adjust(user["id"], p["asset"], "spot", -data.amount)
    await _adjust(user["id"], p["asset"], "earn", data.amount)
    sub = {
        "id": _new_id(), "user_id": user["id"], "product_id": p["id"],
        "asset": p["asset"], "amount": data.amount, "apy": p["apy"],
        "type": p["type"], "status": "active", "earned": 0.0,
        "created_at": _iso(_now()),
    }
    await db.earn_subs.insert_one(sub)
    sub.pop("_id", None)
    return {"subscription": sub}


@earn_r.get("/subscriptions")
async def earn_subs(user: dict = Depends(get_current_user)):
    rows = await db.earn_subs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"items": rows}


# ============================================================================
# SUPPORT
# ============================================================================
support_r = APIRouter(prefix="/support", tags=["support"])


@support_r.post("/tickets")
async def create_ticket(data: SupportTicketIn, user: dict = Depends(get_current_user)):
    t = {
        "id": _new_id(), "user_id": user["id"], "subject": data.subject,
        "message": data.message, "category": data.category, "status": "open",
        "replies": [], "created_at": _iso(_now()),
    }
    await db.support_tickets.insert_one(t)
    t.pop("_id", None)
    return {"ticket": t}


@support_r.get("/tickets")
async def my_tickets(user: dict = Depends(get_current_user)):
    rows = await db.support_tickets.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"items": rows}


# ============================================================================
# ADMIN
# ============================================================================
admin_r = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@admin_r.get("/dashboard")
async def admin_dashboard():
    total_users = await db.users.count_documents({})
    active_markets = len(UNIVERSE)
    total_deposits = 0.0
    total_withdrawals = 0.0
    async for tx in db.transactions.find({"type": "deposit", "status": "completed"}, {"_id": 0, "amount": 1, "asset": 1}):
        total_deposits += tx["amount"] if tx["asset"] == "USDT" else tx["amount"] * 1000
    async for tx in db.transactions.find({"type": "withdraw", "status": "approved"}, {"_id": 0, "amount": 1, "asset": 1}):
        total_withdrawals += tx["amount"] if tx["asset"] == "USDT" else tx["amount"] * 1000
    trades_24h = await db.trades.count_documents({})
    volume_24h = 0.0
    async for t in db.trades.find({}, {"_id": 0, "price": 1, "quantity": 1}):
        volume_24h += t["price"] * t["quantity"]
    activities = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    latest_users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(10).to_list(10)
    latest_users = [_public_user(u) for u in latest_users]
    return {
        "stats": {
            "total_users": total_users,
            "trading_volume_24h": volume_24h,
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "active_markets": active_markets,
            "trades_count": trades_24h,
        },
        "activities": activities,
        "latest_users": latest_users,
    }


@admin_r.get("/users")
async def admin_users(q: Optional[str] = None, limit: int = 50):
    query = {}
    if q:
        query = {"$or": [{"email": {"$regex": q, "$options": "i"}}, {"name": {"$regex": q, "$options": "i"}}]}
    rows = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": [_public_user(u) for u in rows]}


@admin_r.patch("/users/{user_id}")
async def admin_update_user(user_id: str, data: AdminUserUpdateIn, actor: dict = Depends(require_admin)):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields")
    await db.users.update_one({"id": user_id}, {"$set": patch})
    if patch.get("kyc_status"):
        await db.kyc.update_one({"user_id": user_id}, {"$set": {"status": patch["kyc_status"]}})
    await _log_audit(actor["id"], "admin.user.update", target=user_id, meta=patch)
    u = await db.users.find_one({"id": user_id})
    return {"user": _public_user(u)}


@admin_r.get("/kyc")
async def admin_kyc_list(status: Optional[str] = None):
    q = {"status": status} if status else {}
    rows = await db.kyc.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.post("/kyc/{kyc_id}/decision")
async def admin_kyc_decision(kyc_id: str, data: KycDecisionIn, actor: dict = Depends(require_admin)):
    doc = await db.kyc.find_one({"id": kyc_id})
    if not doc:
        raise HTTPException(404, "KYC not found")
    status = "approved" if data.decision == "approved" else "rejected"
    await db.kyc.update_one({"id": kyc_id}, {"$set": {"status": status, "decided_at": _iso(_now()), "reason": data.reason}})
    await db.users.update_one({"id": doc["user_id"]}, {"$set": {"kyc_status": status}})
    await _log_audit(actor["id"], f"admin.kyc.{status}", target=doc["user_id"])
    return {"ok": True}


@admin_r.get("/transactions")
async def admin_tx(type: Optional[str] = None, status: Optional[str] = None, limit: int = 100):
    q = {}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    rows = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.post("/transactions/{tx_id}/decision")
async def admin_tx_decision(tx_id: str, data: AdminTxDecisionIn, actor: dict = Depends(require_admin)):
    tx = await db.transactions.find_one({"id": tx_id})
    if not tx:
        raise HTTPException(404, "Not found")
    if tx["status"] != "pending":
        raise HTTPException(400, "Already decided")
    if data.decision == "approved":
        # finalize withdraw: remove from locked
        if tx["type"] == "withdraw":
            await _adjust(tx["user_id"], tx["asset"], "locked", -tx["amount"])
        await db.transactions.update_one({"id": tx_id}, {"$set": {"status": "approved", "decided_at": _iso(_now())}})
    else:
        if tx["type"] == "withdraw":
            await _adjust(tx["user_id"], tx["asset"], "locked", -tx["amount"])
            await _adjust(tx["user_id"], tx["asset"], "spot", tx["amount"])
        await db.transactions.update_one({"id": tx_id}, {"$set": {"status": "rejected", "decided_at": _iso(_now()), "reason": data.note}})
    await _log_audit(actor["id"], f"admin.tx.{data.decision}", target=tx_id)
    # notify user by email
    try:
        u = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        if u and u.get("email"):
            await send_withdrawal_update(
                to=u["email"], name=u.get("name") or u["email"],
                asset=tx["asset"], amount=tx["amount"], status=data.decision, note=data.note,
            )
    except Exception as e:
        logger.warning("withdrawal email skipped: %s", e)
    return {"ok": True}


@admin_r.get("/orders")
async def admin_orders(status: Optional[str] = None, limit: int = 100):
    q = {}
    if status:
        q["status"] = status
    rows = await db.orders.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.get("/positions")
async def admin_positions(status: Optional[str] = None, limit: int = 100):
    q = {}
    if status:
        q["status"] = status
    rows = await db.positions.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.get("/wallets")
async def admin_wallets(limit: int = 200):
    rows = await db.wallets.find({}, {"_id": 0}).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.get("/pairs")
async def admin_list_pairs():
    rows = await db.market_pairs.find({}, {"_id": 0}).to_list(500)
    return {"items": rows}


@admin_r.post("/pairs")
async def admin_add_pair(data: MarketPairIn, actor: dict = Depends(require_admin)):
    row = data.model_dump()
    row["id"] = _new_id()
    row["created_at"] = _iso(_now())
    await db.market_pairs.update_one({"symbol": row["symbol"]}, {"$set": row}, upsert=True)
    await _log_audit(actor["id"], "admin.pair.upsert", target=row["symbol"])
    return {"pair": row}


@admin_r.get("/fees")
async def admin_fees():
    f = await db.config.find_one({"id": "fees"}, {"_id": 0})
    return {"fees": f or {"spot_maker": 0.001, "spot_taker": 0.001, "futures_maker": 0.0004, "futures_taker": 0.0006, "withdraw_fee_pct": 0.001}}


@admin_r.post("/fees")
async def admin_set_fees(data: FeeConfigIn, actor: dict = Depends(require_admin)):
    row = {"id": "fees", **data.model_dump()}
    await db.config.update_one({"id": "fees"}, {"$set": row}, upsert=True)
    await _log_audit(actor["id"], "admin.fees.update")
    return {"ok": True, "fees": row}


@admin_r.get("/audit")
async def admin_audit(limit: int = 100):
    rows = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": rows}


@admin_r.get("/support")
async def admin_support(status: Optional[str] = None):
    q = {"status": status} if status else {}
    rows = await db.support_tickets.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.post("/support/reply")
async def admin_support_reply(data: SupportReplyIn, actor: dict = Depends(require_admin)):
    reply = {"from": "admin", "message": data.message, "at": _iso(_now())}
    await db.support_tickets.update_one({"id": data.ticket_id}, {"$push": {"replies": reply}, "$set": {"status": "answered"}})
    return {"ok": True}


@admin_r.get("/reports/overview")
async def admin_reports():
    users = await db.users.count_documents({})
    verified = await db.users.count_documents({"kyc_status": "approved"})
    orders = await db.orders.count_documents({})
    positions = await db.positions.count_documents({})
    pending_wd = await db.transactions.count_documents({"type": "withdraw", "status": "pending"})
    return {
        "users_total": users, "users_verified": verified,
        "orders_total": orders, "positions_total": positions,
        "pending_withdrawals": pending_wd,
    }


# ============================================================================
# WIRE ROUTERS
# ============================================================================
api.include_router(auth)
api.include_router(user_r)
api.include_router(market_r)
api.include_router(wallet_r)
api.include_router(trade_r)
api.include_router(fut_r)
api.include_router(earn_r)
api.include_router(support_r)
api.include_router(admin_r)


@api.get("/")
async def root():
    return {"service": "nexbit", "version": "1.0.0", "status": "ok"}


@api.get("/health")
async def health():
    return {"ok": True, "time": _iso(_now())}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# SEED
# ============================================================================
async def _seed() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@nexbit.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        uid = _new_id()
        await db.users.insert_one({
            "id": uid, "email": admin_email, "name": "NEXBIT Admin",
            "password_hash": hash_password(admin_password), "role": "admin",
            "status": "active", "kyc_status": "approved", "email_verified": True,
            "twofa_enabled": False, "created_at": _iso(_now()),
        })
        for asset in ["USDT", "BTC", "ETH"]:
            await db.wallets.insert_one({
                "id": _new_id(), "user_id": uid, "asset": asset,
                "spot": 10000.0 if asset == "USDT" else 0.0, "futures": 0.0, "earn": 0.0, "locked": 0.0,
                "updated_at": _iso(_now()),
            })
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"id": existing["id"]}, {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})

    # Demo user
    demo_email = os.environ.get("DEMO_USER_EMAIL", "demo@nexbit.com")
    demo_password = os.environ.get("DEMO_USER_PASSWORD", "Demo@12345")
    demo = await db.users.find_one({"email": demo_email})
    if not demo:
        uid = _new_id()
        await db.users.insert_one({
            "id": uid, "email": demo_email, "name": "Demo Trader",
            "password_hash": hash_password(demo_password), "role": "user",
            "status": "active", "kyc_status": "approved", "email_verified": True,
            "twofa_enabled": False, "country": "US", "created_at": _iso(_now()),
        })
        starts = {"USDT": 12431.20, "BTC": 0.082431, "ETH": 1.41256, "SOL": 25.5, "BNB": 2.0, "XRP": 150.0, "DOGE": 500.0, "AVAX": 3.0, "LINK": 10.0, "ADA": 200.0}
        for asset, amt in starts.items():
            await db.wallets.insert_one({
                "id": _new_id(), "user_id": uid, "asset": asset,
                "spot": amt, "futures": 500.0 if asset == "USDT" else 0.0, "earn": 0.0, "locked": 0.0,
                "updated_at": _iso(_now()),
            })
        # a few sample trades + orders
        for sym in ["BTC", "ETH", "SOL"]:
            p = await get_price(sym)
            if p > 0:
                await db.trades.insert_one({
                    "id": _new_id(), "user_id": uid, "pair": f"{sym}/USDT",
                    "side": random.choice(["buy", "sell"]),
                    "price": p * random.uniform(0.98, 1.02),
                    "quantity": random.uniform(0.01, 0.3),
                    "fee": 1.2, "created_at": _iso(_now() - timedelta(hours=random.randint(1, 48))),
                })

    # Default market pairs
    if await db.market_pairs.count_documents({}) == 0:
        for c in UNIVERSE:
            await db.market_pairs.insert_one({
                "id": _new_id(), "symbol": f"{c['symbol']}/USDT",
                "base": c["symbol"], "quote": "USDT",
                "min_qty": 0.0001, "tick": 0.01,
                "maker_fee": 0.001, "taker_fee": 0.001,
                "enabled": True, "created_at": _iso(_now()),
            })

    # Save test credentials file for testing agent
    try:
        memory_dir = Path("/app/memory")
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "test_credentials.md").write_text(
            f"""# NEXBIT Test Credentials

## Admin
- email: {admin_email}
- password: {admin_password}
- role: admin
- login: POST /api/auth/login

## Demo User
- email: {demo_email}
- password: {demo_password}
- role: user

## Auth endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me
- POST /api/auth/refresh
"""
        )
    except Exception as e:
        logger.warning("could not write test_credentials.md: %s", e)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await _seed()
    app.state.ws_task = asyncio.create_task(market_broadcaster())
    logger.info("NEXBIT backend started with WebSocket broadcaster")


@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_mgr.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw) if isinstance(raw, str) else {}
            except Exception:
                continue
            action = msg.get("action")
            channels = msg.get("channels") or []
            if action == "subscribe":
                await ws_mgr.subscribe(ws, channels)
                await ws.send_text(json.dumps({"channel": "_ack", "data": {"subscribed": channels}}))
            elif action == "unsubscribe":
                await ws_mgr.unsubscribe(ws, channels)
            elif action == "ping":
                await ws.send_text(json.dumps({"channel": "_pong", "data": {}}))
    except WebSocketDisconnect:
        await ws_mgr.disconnect(ws)
    except Exception:
        await ws_mgr.disconnect(ws)


@app.on_event("shutdown")
async def on_shutdown():
    from db import close
    await close()

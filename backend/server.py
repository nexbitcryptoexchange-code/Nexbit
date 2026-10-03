"""NEXBIT backend — FastAPI monolith with modular route groups."""
import os
import json
import uuid
import secrets
import hashlib
import logging
import asyncio
import random
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from urllib.parse import parse_qs

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

PRODUCTION_MODE = os.environ.get("NEXBIT_PRODUCTION", "false").lower() == "true"

if PRODUCTION_MODE:
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if len(jwt_secret) < 32 or jwt_secret.lower().startswith("change-me"):
        raise RuntimeError("JWT_SECRET must be a strong secret (32+ chars) when NEXBIT_PRODUCTION=true")

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, WebSocket, WebSocketDisconnect
from pymongo.errors import DuplicateKeyError
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
from matching_engine import matching_engine
from financial import to_decimal, to_decimal128
from custody import custody, CustodyNotConfigured, CustodyProviderError
from emailer import send_welcome_verify, send_password_reset, send_withdrawal_update
from models import (
    RegisterIn, LoginIn, ForgotIn, ResetIn, VerifyEmailIn, TwoFAIn, ProfileUpdateIn,
    KycSubmitIn, KycDecisionIn, OrderIn, FuturesOrderIn, ClosePositionIn,
    DepositIn, WithdrawIn, TransferIn, EarnSubscribeIn, ApiKeyIn,
    AdminUserUpdateIn, AdminTxDecisionIn, AdminBalanceAdjustmentIn, MarketPairIn, FeeConfigIn, FeeTreasuryIn,
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


async def _store_refresh_session(user_id: str, refresh_token: str) -> None:
    await db.auth_sessions.insert_one({
        "id": _new_id(),
        "user_id": user_id,
        "token_hash": hashlib.sha256(refresh_token.encode("utf-8")).hexdigest(),
        "expires_at": _now() + timedelta(days=7),
        "revoked": False,
        "created_at": _iso(_now()),
    })


async def _revoke_refresh_session(refresh_token: Optional[str]) -> None:
    if not refresh_token:
        return
    token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    await db.auth_sessions.update_one(
        {"token_hash": token_hash, "revoked": False},
        {"$set": {"revoked": True, "revoked_at": _iso(_now())}},
    )


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


def _mask_document_number(value: Optional[str]) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _public_kyc(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    public_doc = {key: value for key, value in doc.items() if key != "_id"}
    if "document_number" in public_doc:
        public_doc["document_number"] = _mask_document_number(public_doc["document_number"])
    return public_doc


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
        starting = 0.0
        await db.wallets.insert_one({
            "id": _new_id(), "user_id": uid, "asset": asset,
            "spot": starting, "futures": 0.0, "earn": 0.0, "locked": 0.0,
            "updated_at": _iso(_now()),
        })
    access = create_access_token(uid, email, "user")
    refresh = create_refresh_token(uid)
    await _store_refresh_session(uid, refresh)
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
    await _store_refresh_session(u["id"], refresh)
    set_auth_cookies(response, access, refresh)
    await _log_audit(u["id"], "auth.login")
    return {"user": _public_user(u), "access_token": access}


@auth.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    await _revoke_refresh_session(request.cookies.get("refresh_token"))
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
    token_hash = hashlib.sha256(rt.encode("utf-8")).hexdigest()
    claimed = await db.auth_sessions.update_one(
        {"token_hash": token_hash, "user_id": payload["sub"], "revoked": False},
        {"$set": {"revoked": True, "revoked_at": _iso(_now())}},
    )
    if claimed.modified_count != 1:
        raise HTTPException(status_code=401, detail="Refresh token revoked or already used")
    u = await db.users.find_one({"id": payload["sub"]})
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    if u.get("status") in {"banned", "suspended"}:
        raise HTTPException(status_code=403, detail="Account unavailable")
    access = create_access_token(u["id"], u["email"], u.get("role", "user"))
    new_refresh = create_refresh_token(u["id"])
    await _store_refresh_session(u["id"], new_refresh)
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True}


@auth.post("/forgot-password")
async def forgot(data: ForgotIn):
    email = data.email.lower()
    u = await db.users.find_one({"email": email})
    token = secrets.token_urlsafe(32)
    if u:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        await db.password_reset_tokens.insert_one({
            "id": _new_id(), "user_id": u["id"], "token_hash": token_hash,
            "expires_at": _now() + timedelta(hours=1), "used": False,
            "created_at": _iso(_now()),
        })
        try:
            await send_password_reset(to=email, name=u.get("name") or email, token=token)
        except Exception as e:
            logger.warning("reset email send skipped: %s", e)
    # Always return the same response shape without exposing reset tokens.
    return {"ok": True}


@auth.post("/reset-password")
async def reset(data: ResetIn):
    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    rec = await db.password_reset_tokens.find_one({"token_hash": token_hash, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if rec["expires_at"] < _now():
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one({"id": rec["user_id"]}, {"$set": {"password_hash": hash_password(data.password)}})
    await db.password_reset_tokens.update_one({"id": rec["id"]}, {"$set": {"used": True}})
    await db.auth_sessions.update_many(
        {"user_id": rec["user_id"], "revoked": False},
        {"$set": {"revoked": True, "revoked_at": _iso(_now()), "revoke_reason": "password_reset"}},
    )
    return {"ok": True}


@auth.post("/verify-email")
async def verify_email(data: VerifyEmailIn, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]})
    if not u:
        raise HTTPException(404, "User not found")
    if data.code != u.get("verify_code"):
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
    if data.enabled:
        # Do not advertise a security control that is not backed by a real OTP
        # enrollment/challenge flow. Enabling it without enforcement would create
        # a false sense of account protection.
        raise HTTPException(503, "2FA enrollment is not configured yet")
    await db.users.update_one({"id": user["id"]}, {"$set": {"twofa_enabled": False}})
    return {"ok": True, "twofa_enabled": False}


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
    return {"ok": True, "kyc": _public_kyc(doc)}


@user_r.get("/kyc")
async def get_my_kyc(user: dict = Depends(get_current_user)):
    doc = await db.kyc.find_one({"user_id": user["id"]}, {"_id": 0})
    return {"kyc": _public_kyc(doc)}


@user_r.get("/notifications")
async def my_notifications(user: dict = Depends(get_current_user)):
    rows = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"items": rows}


@user_r.post("/api-keys")
async def create_api_key(data: ApiKeyIn, user: dict = Depends(get_current_user)):
    raise HTTPException(
        status_code=503,
        detail="API keys are not enabled until signed API authentication is implemented",
    )


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
    # Referral payouts are not enabled until a real, ledger-backed reward
    # engine is configured. Never expose a synthetic earnings amount.
    return {
        "code": code,
        "referrals": referrals,
        "earnings_usdt": 0.0,
        "rewards_enabled": False,
    }


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
    if interval not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
        raise HTTPException(400, "Unsupported interval")
    seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[interval]
    pair = f"{sym}/USDT"
    trades = await db.trades.find(
        {"pair": pair},
        {"_id": 0, "price": 1, "quantity": 1, "created_at": 1},
    ).sort("created_at", 1).limit(5000).to_list(5000)
    buckets = {}
    for tr in trades:
        try:
            dt = datetime.fromisoformat(tr["created_at"])
            ts = int(dt.timestamp())
            bucket = ts - (ts % seconds)
            price = float(tr["price"])
            qty = float(tr["quantity"])
        except Exception:
            continue
        b = buckets.get(bucket)
        if b is None:
            buckets[b] = {"t": bucket, "o": price, "h": price, "l": price, "c": price, "v": qty}
        else:
            b["h"] = max(b["h"], price)
            b["l"] = min(b["l"], price)
            b["c"] = price
            b["v"] += qty
    items = sorted(buckets.values(), key=lambda x: x["t"])[-min(limit, 200):]
    return {"items": items}


@market_r.get("/orderbook/{symbol}")
async def orderbook(symbol: str):
    sym = symbol.upper()
    pair = f"{sym}/USDT"
    rows = await db.orders.find(
        {"pair": pair, "status": {"$in": ["open", "partial"]}, "type": "limit"},
        {"_id": 0, "side": 1, "price": 1, "quantity": 1, "filled_qty": 1},
    ).to_list(5000)
    bids = []
    asks = []
    for row in rows:
        remaining = max(0.0, float(row.get("quantity", 0)) - float(row.get("filled_qty", 0)))
        if remaining <= 0:
            continue
        level = {"price": float(row["price"]), "qty": remaining}
        (bids if row["side"] == "buy" else asks).append(level)
    bids.sort(key=lambda x: x["price"], reverse=True)
    asks.sort(key=lambda x: x["price"])
    return {"bids": bids[:100], "asks": asks[:100]}


@market_r.get("/trades/{symbol}")
async def recent_trades(symbol: str):
    pair = f"{symbol.upper()}/USDT"
    rows = await db.trades.find(
        {"pair": pair},
        {"_id": 0, "created_at": 1, "price": 1, "quantity": 1, "side": 1},
    ).sort("created_at", -1).limit(100).to_list(100)
    items = []
    for row in rows:
        items.append({
            "t": row.get("created_at"),
            "price": float(row.get("price") or 0),
            "qty": float(row.get("quantity") or 0),
            "side": row.get("side"),
        })
    return {"items": items}


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


async def _get_wallet(uid: str, asset: str, session=None) -> dict:
    asset = asset.upper()
    w = await db.wallets.find_one({"user_id": uid, "asset": asset}, session=session)
    if not w:
        w = {"id": _new_id(), "user_id": uid, "asset": asset,
             "spot": to_decimal128("0"), "futures": to_decimal128("0"),
             "earn": to_decimal128("0"), "locked": to_decimal128("0"),
             "updated_at": _iso(_now())}
        await db.wallets.insert_one(w, session=session)
    else:
        fields = ("spot", "futures", "earn", "locked")
        if any(not hasattr(w.get(field), "to_decimal") for field in fields):
            converted = {field: to_decimal128(w.get(field, 0)) for field in fields}
            await db.wallets.update_one(
                {"user_id": uid, "asset": asset},
                {"$set": {**converted, "updated_at": _iso(_now())}},
                session=session,
            )
            w.update(converted)
    w.pop("_id", None)
    return w

def _public_wallet(wallet: dict) -> dict:
    out = dict(wallet)
    for field in ("spot", "futures", "earn", "locked"):
        out[field] = float(to_decimal(wallet.get(field, 0)))
    return out

def _public_transaction(tx: dict) -> dict:
    out = dict(tx)
    if "amount" in out:
        out["amount"] = float(to_decimal(out["amount"]))
    return out


async def _adjust(
    uid: str,
    asset: str,
    bucket: str,
    delta: float,
    *,
    reason: str = "balance.adjust",
    reference_id: Optional[str] = None,
    session=None,
) -> dict:
    if bucket not in {"spot", "futures", "earn", "locked"}:
        raise HTTPException(500, "Invalid wallet bucket")
    delta = to_decimal(delta)
    if delta == 0:
        return await _get_wallet(uid, asset, session=session)

    asset = asset.upper()
    await _get_wallet(uid, asset, session=session)
    now = _iso(_now())
    delta128 = to_decimal128(delta)
    query = {"user_id": uid, "asset": asset}
    if delta < 0:
        query[bucket] = {"$gte": to_decimal128(-delta)}

    result = await db.wallets.update_one(
        query,
        {"$inc": {bucket: delta128}, "$set": {"updated_at": now}},
        session=session,
    )
    if result.matched_count != 1:
        raise HTTPException(400, f"Insufficient {asset} in {bucket}")

    wallet = await db.wallets.find_one({"user_id": uid, "asset": asset}, {"_id": 0}, session=session)
    balance_after = wallet.get(bucket) or to_decimal128("0")
    await db.ledger_entries.insert_one({
        "id": _new_id(),
        "user_id": uid,
        "asset": asset,
        "bucket": bucket,
        "delta": delta128,
        "balance_after": balance_after,
        "reason": reason,
        "reference_id": reference_id,
        "created_at": now,
    }, session=session)
    return wallet


@wallet_r.get("/balances")
async def balances(user: dict = Depends(get_current_user)):
    rows = await db.wallets.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    prices = await get_prices()
    total_usd = Decimal("0")
    public_rows = []
    for r in rows:
        p = Decimal("1") if r["asset"] == "USDT" else Decimal(str((prices.get(r["asset"]) or {}).get("price", 0.0)))
        total = sum((to_decimal(r.get(field, 0)) for field in ("spot", "futures", "earn", "locked")), Decimal("0"))
        public = _public_wallet(r)
        public["usd_value"] = float(total * p)
        public["price"] = float(p)
        public["total"] = float(total)
        public_rows.append(public)
        total_usd += total * p
    public_rows.sort(key=lambda x: -x["usd_value"])
    return {"total_usd": float(total_usd), "items": public_rows}


@wallet_r.get("/transactions")
async def transactions(user: dict = Depends(get_current_user), limit: int = 100):
    rows = await db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": [_public_transaction(row) for row in rows]}


@wallet_r.get("/deposit/address")
async def deposit_address(
    asset: str,
    network: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    asset = asset.upper().strip()
    network = (network or asset).upper().strip()
    if not asset or not network:
        raise HTTPException(400, "Asset and network are required")
    if not (PRODUCTION_MODE and os.environ.get("NEXBIT_CUSTODY_ENABLED", "false").lower() == "true"):
        raise HTTPException(503, "On-chain deposit custody is not enabled")
    existing = await db.wallet_addresses.find_one(
        {"user_id": user["id"], "asset": asset, "network": network},
        {"_id": 0},
    )
    if existing:
        return {"address": existing}
    try:
        created = await custody.create_deposit_address(user["id"], asset, network)
    except (CustodyNotConfigured, CustodyProviderError) as exc:
        raise HTTPException(503, str(exc))
    now = _iso(_now())
    row = {
        "id": _new_id(),
        "user_id": user["id"],
        "asset": asset,
        "network": network,
        "address": created["address"],
        "ticker": created["ticker"],
        "callback_url": created["callback_url"],
        "minimum_transaction": created.get("minimum_transaction"),
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.wallet_addresses.insert_one(row)
    except Exception:
        existing = await db.wallet_addresses.find_one(
            {"user_id": user["id"], "asset": asset, "network": network},
            {"_id": 0},
        )
        if existing:
            return {"address": existing}
        raise
    row.pop("_id", None)
    await _log_audit(
        user["id"],
        "wallet.deposit.address.create",
        meta={"asset": asset, "network": network},
    )
    return {"address": row}


@wallet_r.post("/deposit")
async def deposit(data: DepositIn, user: dict = Depends(get_current_user)):
    # Balance credits come only from verified BlockBee confirmation webhooks
    # or the explicit admin ledger adjustment route.
    raise HTTPException(410, "Use /api/wallet/deposit/address to get a deposit address")


@wallet_r.post("/withdraw")
async def withdraw(data: WithdrawIn, user: dict = Depends(get_current_user)):
    asset = data.asset.upper().strip()
    network = (data.network or asset).upper().strip()
    address = data.address.strip()

    if not asset or not network:
        raise HTTPException(400, "Asset and network are required")
    if len(address) < 8 or len(address) > 256:
        raise HTTPException(400, "Invalid withdrawal address")
    try:
        custody.validate_asset_network(asset, network)
    except CustodyProviderError as exc:
        raise HTTPException(400, str(exc))

    now = _iso(_now())
    tx = {
        "id": _new_id(), "user_id": user["id"], "type": "withdraw",
        "asset": asset, "amount": to_decimal128(data.amount), "status": "pending",
        "address": address, "network": network,
        "reference_id": _new_id(),
        "created_at": now,
    }
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            await _adjust(user["id"], asset, "spot", -data.amount, session=session)
            await _adjust(user["id"], asset, "locked", data.amount, session=session)
            await db.transactions.insert_one(tx, session=session)
    tx.pop("_id", None)
    public_tx = _public_transaction(tx)
    await _log_audit(
        user["id"], "wallet.withdraw.request",
        target=tx["id"],
        meta={"asset": asset, "amount": public_tx["amount"], "network": network},
    )
    return {"tx": public_tx}


@wallet_r.post("/transfer")
async def transfer(data: TransferIn, user: dict = Depends(get_current_user)):
    if data.from_wallet == data.to_wallet:
        raise HTTPException(400, "Source and destination must differ")
    if data.amount <= 0:
        raise HTTPException(400, "Transfer amount must be positive")
    if data.from_wallet not in {"spot", "futures", "earn"} or data.to_wallet not in {"spot", "futures", "earn"}:
        raise HTTPException(400, "Invalid wallet bucket")

    asset = data.asset.upper().strip()
    tx = {
        "id": _new_id(), "user_id": user["id"], "type": "transfer",
        "asset": asset, "amount": to_decimal128(data.amount), "status": "completed",
        "from_wallet": data.from_wallet, "to_wallet": data.to_wallet,
        "reference_id": _new_id(),
        "created_at": _iso(_now()),
    }
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            await _adjust(user["id"], asset, data.from_wallet, -data.amount, session=session)
            await _adjust(user["id"], asset, data.to_wallet, data.amount, session=session)
            await db.transactions.insert_one(tx, session=session)
    tx.pop("_id", None)
    public_tx = _public_transaction(tx)
    await _log_audit(
        user["id"], "wallet.transfer",
        target=tx["id"], meta={"asset": asset, "amount": public_tx["amount"], "from": data.from_wallet, "to": data.to_wallet},
    )
    return {"tx": public_tx}


@api.post("/webhooks/blockbee/deposit")
async def blockbee_deposit_webhook(request: Request):
    if not custody.enabled:
        raise HTTPException(503, "BlockBee custody is not configured")
    raw = await request.body()
    signature = request.headers.get("x-ca-signature", "")
    if not custody.verify_signature(raw, signature):
        logger.warning("Rejected BlockBee deposit webhook: invalid signature")
        raise HTTPException(401, "Invalid signature")

    fields = {key: values[-1] for key, values in parse_qs(raw.decode("utf-8"), keep_blank_values=True).items()}
    user_id = fields.get("user_id", "")
    nonce = fields.get("nonce", "")
    uuid_value = fields.get("uuid", "")
    address_in = fields.get("address_in", "")
    pending = fields.get("pending", "")
    asset = fields.get("asset", "").upper()
    network = fields.get("network", "").upper()
    if not user_id or not nonce or not uuid_value or not address_in or not asset or not network:
        raise HTTPException(400, "Incomplete BlockBee deposit webhook")

    address = await db.wallet_addresses.find_one(
        {"user_id": user_id, "asset": asset, "network": network, "address": address_in},
        {"_id": 0},
    )
    if not address:
        raise HTTPException(404, "Unknown deposit address")
    if f"nonce={nonce}" not in address.get("callback_url", ""):
        raise HTTPException(403, "Invalid deposit nonce")

    if pending == "1":
        await db.blockchain_events.update_one(
            {"provider": "blockbee", "event_id": uuid_value},
            {"$set": {
                "provider": "blockbee", "event_id": uuid_value, "user_id": user_id,
                "asset": asset, "network": network, "address": address_in,
                "txid_in": fields.get("txid_in"), "pending": True,
                "status": "pending", "updated_at": _iso(_now()),
            }},
            upsert=True,
        )
        return Response(content="*ok*", media_type="text/plain")

    try:
        amount = Decimal(str(fields.get("value_forwarded_coin") or fields.get("value_coin") or 0))
    except ValueError:
        raise HTTPException(400, "Invalid deposit amount")
    if amount <= 0:
        raise HTTPException(400, "Invalid deposit amount")

    now = _iso(_now())
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            event = await db.blockchain_events.find_one(
                {"provider": "blockbee", "event_id": uuid_value},
                {"_id": 0},
                session=session,
            )
            if event and event.get("status") == "confirmed":
                return Response(content="*ok*", media_type="text/plain")
            await db.blockchain_events.update_one(
                {"provider": "blockbee", "event_id": uuid_value},
                {"$set": {
                    "provider": "blockbee", "event_id": uuid_value, "user_id": user_id,
                    "asset": asset, "network": network, "address": address_in,
                    "txid_in": fields.get("txid_in"), "pending": False,
                    "status": "processing", "updated_at": now,
                }},
                upsert=True,
                session=session,
            )
            existing_tx = await db.transactions.find_one(
                {"type": "deposit", "reference_id": uuid_value},
                {"_id": 0},
                session=session,
            )
            if existing_tx and existing_tx.get("status") == "completed":
                await db.blockchain_events.update_one(
                    {"provider": "blockbee", "event_id": uuid_value},
                    {"$set": {"status": "confirmed", "updated_at": now}},
                    session=session,
                )
                return Response(content="*ok*", media_type="text/plain")

            await db.wallets.update_one(
                {"user_id": user_id, "asset": asset},
                {"$setOnInsert": {
                    "id": _new_id(), "user_id": user_id, "asset": asset,
                    "spot": 0.0, "futures": 0.0, "earn": 0.0, "locked": 0.0,
                    "updated_at": now,
                }},
                upsert=True,
                session=session,
            )
            await db.wallets.update_one(
                {"user_id": user_id, "asset": asset},
                {"$inc": {"spot": to_decimal128(amount)}, "$set": {"updated_at": now}},
                session=session,
            )
            wallet = await db.wallets.find_one(
                {"user_id": user_id, "asset": asset},
                {"_id": 0},
                session=session,
            )
            await db.ledger_entries.insert_one({
                "id": _new_id(), "user_id": user_id, "asset": asset, "bucket": "spot",
                "delta": to_decimal128(amount), "balance_after": wallet.get("spot") or to_decimal128("0"),
                "reason": "blockbee.deposit.confirmed", "reference_id": uuid_value, "created_at": now,
            }, session=session)
            await db.transactions.insert_one({
                "id": _new_id(), "user_id": user_id, "type": "deposit", "asset": asset,
                "amount": to_decimal128(amount), "status": "completed", "address": address_in,
                "network": network, "txid": fields.get("txid_in"), "provider": "blockbee",
                "reference_id": uuid_value, "created_at": now,
            }, session=session)
            await db.blockchain_events.update_one(
                {"provider": "blockbee", "event_id": uuid_value},
                {"$set": {
                    "status": "confirmed", "amount": amount, "txid_out": fields.get("txid_out"),
                    "confirmations": int(fields.get("confirmations") or 0), "updated_at": now,
                }},
                session=session,
            )

    await _log_audit(
        user_id, "wallet.deposit.confirmed",
        meta={"asset": asset, "network": network, "amount": amount, "uuid": uuid_value},
    )
    return Response(content="*ok*", media_type="text/plain")

@api.post("/webhooks/blockbee/payout")
async def blockbee_payout_webhook(request: Request):
    if not custody.enabled:
        raise HTTPException(503, "BlockBee custody is not configured")
    raw = await request.body()
    signature = request.headers.get("x-ca-signature", "")
    if not custody.verify_signature(raw, signature):
        logger.warning("Rejected BlockBee payout webhook: invalid signature")
        raise HTTPException(401, "Invalid signature")
    fields = {key: values[-1] for key, values in parse_qs(raw.decode("utf-8"), keep_blank_values=True).items()}
    payout_id = fields.get("id", "")
    status = fields.get("status", "").lower()
    if not payout_id or status not in {"done", "error", "expired"}:
        raise HTTPException(400, "Invalid BlockBee payout webhook")
    if payout_id == "00000000-0000-0000-0000-000000000000":
        return Response(content="*ok*", media_type="text/plain")

    event_id = f"{payout_id}:{status}"
    now = _iso(_now())
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                existing_event = await db.payout_events.find_one(
                    {"provider": "blockbee", "event_id": event_id},
                    {"_id": 0}, session=session,
                )
                if existing_event:
                    return Response(content="*ok*", media_type="text/plain")

                tx = await db.transactions.find_one(
                    {"type": "withdraw", "payout_id": payout_id},
                    {"_id": 0}, session=session,
                )
                if not tx:
                    raise HTTPException(404, "Withdrawal not found")

                await db.payout_events.insert_one({
                    "provider": "blockbee", "event_id": event_id, "payout_id": payout_id,
                    "status": status, "transaction_id": tx["id"], "created_at": now,
                }, session=session)

                if status == "done":
                    await db.transactions.update_one(
                        {"id": tx["id"], "status": {"$in": ["pending", "processing"]}},
                        {"$set": {"status": "completed", "completed_at": now, "payout_status": "done"}},
                        session=session,
                    )
                else:
                    changed = await db.transactions.update_one(
                        {"id": tx["id"], "status": {"$in": ["pending", "processing"]}},
                        {"$set": {
                            "status": "failed", "payout_status": status,
                            "failure_reason": fields.get("error") or status, "failed_at": now,
                        }},
                        session=session,
                    )
                    if changed.modified_count:
                        await _adjust(tx["user_id"], tx["asset"], "locked", -tx["amount"], session=session)
                        await _adjust(tx["user_id"], tx["asset"], "spot", tx["amount"], session=session)
    except DuplicateKeyError:
        return Response(content="*ok*", media_type="text/plain")

    await _log_audit(
        tx["user_id"], f"wallet.withdraw.{status}", target=tx["id"],
        meta={"payout_id": payout_id, "error": fields.get("error")},
    )
    return Response(content="*ok*", media_type="text/plain")





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
    if user.get("status") != "active":
        raise HTTPException(403, "Trading is unavailable for this account")
    order = await matching_engine.place(data, user)
    await _log_audit(
        user["id"],
        "trade.order",
        target=order["id"],
        meta={
            "pair": order["pair"],
            "side": order["side"],
            "type": order["type"],
            "quantity": order["quantity"],
            "filled_qty": order.get("filled_qty", 0),
        },
    )
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
    order = await matching_engine.cancel(order_id, user)
    await _log_audit(user["id"], "trade.order.cancel", target=order_id)
    return {"ok": True, "order": order}


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
    # Futures are fail-closed until a real execution/mark-price provider is configured.
    # Never create a synthetic position or credit/debit balances from a demo price feed.
    if os.environ.get("NEXBIT_FUTURES_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Futures trading is not enabled until a real execution provider is configured")
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
    if os.environ.get("NEXBIT_FUTURES_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Futures trading is not enabled until a real execution provider is configured")
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
    # Do not move customer funds into an earn bucket unless an actual yield/staking
    # provider and redemption flow are configured.
    if os.environ.get("NEXBIT_EARN_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Earn products are not enabled until a real yield provider is configured")
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
async def admin_dashboard(actor: dict = Depends(require_admin)):
    total_users = await db.users.count_documents({})
    active_markets = len(UNIVERSE)
    total_deposits = 0.0
    total_withdrawals = 0.0
    deposits_by_asset = {}
    withdrawals_by_asset = {}
    async for tx in db.transactions.find({"type": "deposit", "status": "completed"}, {"_id": 0, "amount": 1, "asset": 1}):
        asset = str(tx.get("asset") or "").upper()
        amount = float(tx.get("amount") or 0)
        deposits_by_asset[asset] = deposits_by_asset.get(asset, 0.0) + amount
        if asset == "USDT":
            total_deposits += amount
    async for tx in db.transactions.find({"type": "withdraw", "status": "completed"}, {"_id": 0, "amount": 1, "asset": 1}):
        asset = str(tx.get("asset") or "").upper()
        amount = float(tx.get("amount") or 0)
        withdrawals_by_asset[asset] = withdrawals_by_asset.get(asset, 0.0) + amount
        if asset == "USDT":
            total_withdrawals += amount
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
            "deposits_by_asset": deposits_by_asset,
            "withdrawals_by_asset": withdrawals_by_asset,
            "active_markets": active_markets,
            "trades_count": trades_24h,
        },
        "activities": activities,
        "latest_users": latest_users,
    }


@admin_r.get("/users")
async def admin_users(q: Optional[str] = None, limit: int = 50, actor: dict = Depends(require_admin)):
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
async def admin_kyc_list(status: Optional[str] = None, actor: dict = Depends(require_admin)):
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
async def admin_tx(type: Optional[str] = None, status: Optional[str] = None, limit: int = 100, actor: dict = Depends(require_admin)):
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
    if tx["status"] not in {"pending", "submitting"}:
        raise HTTPException(400, "Already decided")

    if data.decision == "rejected":
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                changed = await db.transactions.update_one(
                    {"id": tx_id, "status": "pending"},
                    {"$set": {
                        "status": "rejected",
                        "decided_at": _iso(_now()),
                        "reason": data.note,
                    }},
                    session=session,
                )
                if changed.modified_count != 1:
                    raise HTTPException(409, "Withdrawal is already being processed")
                if tx["type"] == "withdraw":
                    await _adjust(tx["user_id"], tx["asset"], "locked", -tx["amount"], session=session)
                    await _adjust(tx["user_id"], tx["asset"], "spot", tx["amount"], session=session)
        await _log_audit(actor["id"], "admin.tx.rejected", target=tx_id)
    elif tx["type"] != "withdraw":
        changed = await db.transactions.update_one(
            {"id": tx_id, "status": "pending"},
            {"$set": {"status": "approved", "decided_at": _iso(_now())}},
        )
        if changed.modified_count != 1:
            raise HTTPException(409, "Transaction is already decided")
        await _log_audit(actor["id"], "admin.tx.approved", target=tx_id)
    else:
        custody_enabled = os.environ.get("NEXBIT_CUSTODY_ENABLED", "false").lower() == "true"
        custody_provider = os.environ.get("NEXBIT_CUSTODY_PROVIDER", "").strip().lower()
        if not (PRODUCTION_MODE and custody_enabled and custody_provider == "blockbee" and custody.enabled):
            raise HTTPException(
                503,
                "Withdrawal custody is not configured; withdrawal remains pending",
            )
        if tx.get("payout_id"):
            raise HTTPException(400, "Withdrawal payout already submitted")

        try:
            custody.validate_asset_network(tx["asset"], tx.get("network") or tx["asset"])
        except CustodyProviderError as exc:
            raise HTTPException(400, str(exc))

        # Claim the withdrawal before contacting the external provider. This closes
        # the two-admin race: only one admin can move pending -> submitting.
        claimed_at = _iso(_now())
        claim = await db.transactions.update_one(
            {"id": tx_id, "status": "pending", "payout_id": {"$exists": False}},
            {"$set": {
                "status": "submitting",
                "submission_started_at": claimed_at,
                "submission_actor_id": actor["id"],
            }},
        )
        if claim.modified_count != 1:
            raise HTTPException(409, "Withdrawal is already being processed")

        try:
            payout = await custody.create_withdrawal(
                tx["asset"],
                tx.get("network") or tx["asset"],
                tx["address"],
                tx["amount"],
            )
        except (CustodyNotConfigured, CustodyProviderError) as exc:
            await db.transactions.update_one(
                {"id": tx_id, "status": "submitting"},
                {"$set": {
                    "status": "pending",
                    "submission_error": str(exc),
                    "submission_failed_at": _iso(_now()),
                }},
            )
            raise HTTPException(502, str(exc))

        now = _iso(_now())
        updated = await db.transactions.update_one(
            {"id": tx_id, "status": "submitting"},
            {"$set": {
                "status": "processing",
                "payout_id": payout["payout_id"],
                "payout_request_id": payout["request_id"],
                "payout_status": payout.get("status", "processing"),
                "provider": "blockbee",
                "approved_at": now,
                "decided_at": now,
            }},
        )
        if updated.modified_count != 1:
            raise HTTPException(409, "Withdrawal submission state changed unexpectedly")
        await _log_audit(actor["id"], "admin.tx.approved", target=tx_id, meta={"payout_id": payout["payout_id"]})

    # Notify only after the local decision/submission state is committed.
    try:
        u = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        if u and u.get("email"):
            await send_withdrawal_update(
                to=u["email"], name=u.get("name") or u["email"],
                asset=tx["asset"], amount=tx["amount"],
                status="approved" if data.decision == "approved" else "rejected",
                note=data.note,
            )
    except Exception as e:
        logger.warning("withdrawal email skipped: %s", e)
    return {"ok": True}


@admin_r.get("/orders")
async def admin_orders(status: Optional[str] = None, limit: int = 100, actor: dict = Depends(require_admin)):
    q = {}
    if status:
        q["status"] = status
    rows = await db.orders.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.get("/positions")
async def admin_positions(status: Optional[str] = None, limit: int = 100, actor: dict = Depends(require_admin)):
    q = {}
    if status:
        q["status"] = status
    rows = await db.positions.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.get("/wallets")
async def admin_wallets(limit: int = 200, actor: dict = Depends(require_admin)):
    rows = await db.wallets.find({}, {"_id": 0}).limit(limit).to_list(limit)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.post("/wallets/adjust")
async def admin_wallet_adjustment(
    data: AdminBalanceAdjustmentIn,
    actor: dict = Depends(require_admin),
):
    target = await db.users.find_one({"id": data.user_id}, {"_id": 0, "id": 1, "email": 1, "status": 1})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("status") == "banned":
        raise HTTPException(400, "Cannot adjust a banned user")

    asset = data.asset.upper()
    reference_id = data.reference_id or _new_id()
    existing = await db.transactions.find_one({"type": "admin_adjustment", "reference_id": reference_id}, {"_id": 0})
    if existing:
        return {"tx": existing, "duplicate": True}

    delta = data.amount if data.action == "credit" else -data.amount
    reason = "admin.balance.credit" if delta > 0 else "admin.balance.debit"
    tx = {
        "id": _new_id(), "user_id": data.user_id, "type": "admin_adjustment",
        "asset": asset, "amount": to_decimal128(data.amount), "direction": data.action,
        "status": "completed", "bucket": "spot", "reference_id": reference_id,
        "note": data.note, "admin_id": actor["id"], "created_at": _iso(_now()),
    }
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                existing = await db.transactions.find_one(
                    {"type": "admin_adjustment", "reference_id": reference_id},
                    {"_id": 0}, session=session,
                )
                if existing:
                    return {"tx": existing, "duplicate": True}
                wallet = await _adjust(
                    data.user_id, asset, "spot", delta,
                    reason=reason, reference_id=reference_id, session=session,
                )
                await db.transactions.insert_one(tx, session=session)
    except DuplicateKeyError:
        existing = await db.transactions.find_one(
            {"type": "admin_adjustment", "reference_id": reference_id}, {"_id": 0}
        )
        if existing:
            return {"tx": existing, "duplicate": True}
        raise

    await _log_audit(
        actor["id"], reason, target=data.user_id,
        meta={"asset": asset, "amount": data.amount, "reference_id": reference_id, "note": data.note},
    )
    tx.pop("_id", None)
    return {"tx": _public_transaction(tx), "wallet": _public_wallet(wallet)}


@admin_r.get("/pairs")
async def admin_list_pairs(actor: dict = Depends(require_admin)):
    rows = await db.market_pairs.find({}, {"_id": 0}).to_list(500)
    return {"items": rows}


@admin_r.post("/pairs")
async def admin_add_pair(data: MarketPairIn, actor: dict = Depends(require_admin)):
    row = data.model_dump()
    row["symbol"] = row["symbol"].upper()
    row["base"] = row["base"].upper()
    row["quote"] = row["quote"].upper()
    row["id"] = _new_id()
    row["created_at"] = _iso(_now())
    await db.market_pairs.update_one({"symbol": row["symbol"]}, {"$set": row}, upsert=True)
    await _log_audit(actor["id"], "admin.pair.upsert", target=row["symbol"])
    return {"pair": row}


@admin_r.get("/fees")
async def admin_fees(actor: dict = Depends(require_admin)):
    f = await db.config.find_one({"id": "fees"}, {"_id": 0})
    return {"fees": f or {"spot_maker": 0.001, "spot_taker": 0.001, "futures_maker": 0.0004, "futures_taker": 0.0006, "withdraw_fee_pct": 0.001}}


@admin_r.post("/fees")
async def admin_set_fees(data: FeeConfigIn, actor: dict = Depends(require_admin)):
    row = {"id": "fees", **data.model_dump()}
    await db.config.update_one({"id": "fees"}, {"$set": row}, upsert=True)
    await _log_audit(actor["id"], "admin.fees.update")
    return {"ok": True, "fees": row}


@admin_r.get("/fees/treasury")
async def admin_get_fee_treasury(actor: dict = Depends(require_admin)):
    row = await db.config.find_one({"id": "fee_treasury"}, {"_id": 0, "user_id": 1})
    return {"user_id": (row or {}).get("user_id")}


@admin_r.post("/fees/treasury")
async def admin_set_fee_treasury(data: FeeTreasuryIn, actor: dict = Depends(require_admin)):
    target = await db.users.find_one(
        {"id": data.user_id, "status": "active"},
        {"_id": 0, "id": 1, "email": 1, "role": 1},
    )
    if not target:
        raise HTTPException(404, "Active treasury user not found")
    quote_assets = await db.market_pairs.distinct("quote", {"enabled": True})
    quote_assets = [str(x).upper() for x in quote_assets if x]
    if not quote_assets:
        quote_assets = ["USDT"]
    for asset in quote_assets:
        await db.wallets.update_one(
            {"user_id": data.user_id, "asset": asset},
            {"$setOnInsert": {
                "id": _new_id(), "user_id": data.user_id, "asset": asset,
                "spot": 0.0, "futures": 0.0, "earn": 0.0, "locked": 0.0,
                "updated_at": _iso(_now()),
            }},
            upsert=True,
        )
    row = {
        "id": "fee_treasury",
        "user_id": data.user_id,
        "updated_at": _iso(_now()),
        "updated_by": actor["id"],
    }
    await db.config.update_one({"id": "fee_treasury"}, {"$set": row}, upsert=True)
    await _log_audit(actor["id"], "admin.fee_treasury.update", target=data.user_id)
    return {"ok": True, "treasury": {"user_id": data.user_id, "email": target["email"], "assets": quote_assets}}


@admin_r.get("/audit")
async def admin_audit(limit: int = 100, actor: dict = Depends(require_admin)):
    rows = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": rows}


@admin_r.get("/support")
async def admin_support(status: Optional[str] = None, actor: dict = Depends(require_admin)):
    q = {"status": status} if status else {}
    rows = await db.support_tickets.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    for r in rows:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
        r["email"] = u.get("email") if u else "?"
    return {"items": rows}


@admin_r.post("/support/reply")
async def admin_support_reply(data: SupportReplyIn, actor: dict = Depends(require_admin)):
    ticket = await db.support_tickets.find_one({"id": data.ticket_id}, {"_id": 0, "id": 1})
    if not ticket:
        raise HTTPException(404, "Support ticket not found")
    reply = {"from": "admin", "message": data.message, "at": _iso(_now()), "admin_id": actor["id"]}
    await db.support_tickets.update_one(
        {"id": data.ticket_id},
        {"$push": {"replies": reply}, "$set": {"status": "answered", "updated_at": _iso(_now())}},
    )
    await _log_audit(actor["id"], "admin.support.reply", target=data.ticket_id)
    return {"ok": True}


@admin_r.get("/reports/overview")
async def admin_reports(actor: dict = Depends(require_admin)):
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
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# SEED
# ============================================================================
async def _seed() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    existing = await db.users.find_one({"email": admin_email}) if admin_email else None
    if not existing and admin_email and admin_password:
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
                "spot": 0.0, "futures": 0.0, "earn": 0.0, "locked": 0.0,
                "updated_at": _iso(_now()),
            })
    elif existing and admin_password and not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"id": existing["id"]}, {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})

    # No demo users, demo balances, or sample trades are ever seeded.
    # Real balances can only originate from the ledger/admin controls or verified
    # on-chain settlement once custody integration is configured.

    # Remove malformed market-pair records created by older/admin input paths.
    await db.market_pairs.delete_many({
        "$or": [
            {"symbol": {"$in": [None, ""]}},
            {"base": {"$in": [None, ""]}},
            {"quote": {"$in": [None, ""]}},
        ]
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

    # No demo credentials are written or seeded. Production test credentials
    # must be supplied externally and are never persisted by the backend.


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

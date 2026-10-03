"""NEXBIT backend end-to-end API tests (iteration 1)."""
import os
import uuid
import time
import pytest
import requests
from pathlib import Path

# Load REACT_APP_BACKEND_URL from frontend/.env (don't default - fail fast if missing)
def _load_base_url() -> str:
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@nexbit.com"
ADMIN_PASSWORD = "Admin@12345"
DEMO_EMAIL = "demo@nexbit.com"
DEMO_PASSWORD = "Demo@12345"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email: str, password: str):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data
    return data["access_token"], data["user"]


@pytest.fixture(scope="session")
def admin_token():
    tok, u = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert u.get("role") == "admin"
    return tok


@pytest.fixture(scope="session")
def demo_token():
    tok, u = _login(DEMO_EMAIL, DEMO_PASSWORD)
    assert u.get("role") == "user"
    return tok


def _hdr(tok: str):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Health ----------
def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---------- Auth ----------
def test_admin_login_cookies_and_role():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["role"] == "admin"
    assert "access_token" in data
    # cookies
    cookie_names = {c.name for c in r.cookies}
    assert "access_token" in cookie_names or "refresh_token" in cookie_names, f"no auth cookies set: {cookie_names}"


def test_demo_login_role_user():
    _tok, u = _login(DEMO_EMAIL, DEMO_PASSWORD)
    assert u["role"] == "user"
    assert u["email"] == DEMO_EMAIL


def test_auth_me(demo_token):
    r = requests.get(f"{API}/auth/me", headers=_hdr(demo_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == DEMO_EMAIL


def test_register_new_user_and_wallets():
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "StrongPass!123", "name": "Test"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == email
    tok = data["access_token"]
    # verify wallets seeded
    r2 = requests.get(f"{API}/wallet/balances", headers=_hdr(tok), timeout=15)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assets = {w["asset"] for w in items}
    assert "USDT" in assets
    usdt = next(w for w in items if w["asset"] == "USDT")
    assert usdt["spot"] >= 1.0


# ---------- Market ----------
def test_market_tickers():
    r = requests.get(f"{API}/market/tickers", timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 12, f"expected >=12 tickers, got {len(items)}"
    row = items[0]
    for k in ("price", "change_24h", "sparkline", "pair"):
        assert k in row


def test_market_candles_btc():
    r = requests.get(f"{API}/market/candles/BTC", timeout=30)
    assert r.status_code == 200
    data = r.json()
    candles = data.get("items") or data.get("candles") or data
    if isinstance(candles, dict) and "items" in candles:
        candles = candles["items"]
    assert isinstance(candles, list)
    assert len(candles) >= 60, f"expected >=60 candles, got {len(candles)}"


def test_market_orderbook_btc():
    r = requests.get(f"{API}/market/orderbook/BTC", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "bids" in data and "asks" in data
    assert len(data["bids"]) == 15
    assert len(data["asks"]) == 15


# ---------- Wallet ----------
def test_wallet_balances(demo_token):
    r = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 5
    pos_usd = [w for w in items if w.get("usd_value", 0) > 0]
    assert len(pos_usd) >= 2


def test_wallet_deposit(demo_token):
    before = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    before_sol = next((w["spot"] for w in before if w["asset"] == "SOL"), 0.0)
    r = requests.post(f"{API}/wallet/deposit", headers=_hdr(demo_token), json={"asset": "SOL", "amount": 5}, timeout=15)
    assert r.status_code == 200, r.text
    tx = r.json()["tx"]
    assert tx["status"] == "completed"
    after = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    after_sol = next((w["spot"] for w in after if w["asset"] == "SOL"), 0.0)
    assert round(after_sol - before_sol, 6) == 5.0


def test_wallet_withdraw_pending(demo_token):
    r = requests.post(f"{API}/wallet/withdraw", headers=_hdr(demo_token),
                      json={"asset": "USDT", "amount": 10, "address": "nxaddr_test", "network": "USDT"}, timeout=15)
    assert r.status_code == 200, r.text
    tx = r.json()["tx"]
    assert tx["status"] == "pending"
    # locked increased
    bal = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    usdt = next(w for w in bal if w["asset"] == "USDT")
    assert usdt["locked"] >= 10


# ---------- Spot trading ----------
def test_spot_market_order_fills(demo_token):
    bal_before = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    usdt_before = next(w["spot"] for w in bal_before if w["asset"] == "USDT")
    r = requests.post(f"{API}/trade/order", headers=_hdr(demo_token),
                      json={"pair": "BTC/USDT", "side": "buy", "type": "market", "quantity": 0.0005}, timeout=20)
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order["status"] == "filled"
    bal_after = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    usdt_after = next(w["spot"] for w in bal_after if w["asset"] == "USDT")
    assert usdt_after < usdt_before


def test_spot_limit_order_open_and_cancel(demo_token):
    # place a far-off limit sell so it stays open
    r = requests.post(f"{API}/trade/order", headers=_hdr(demo_token),
                      json={"pair": "BTC/USDT", "side": "sell", "type": "limit",
                            "quantity": 0.0001, "price": 999999}, timeout=20)
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order["status"] == "open"
    oid = order["id"]
    # list opens
    r2 = requests.get(f"{API}/trade/orders", headers=_hdr(demo_token), params={"status": "open"}, timeout=15)
    assert r2.status_code == 200
    ids = [o["id"] for o in r2.json()["items"]]
    assert oid in ids
    # cancel
    r3 = requests.post(f"{API}/trade/orders/{oid}/cancel", headers=_hdr(demo_token), timeout=15)
    assert r3.status_code == 200
    assert r3.json().get("ok") is True


# ---------- Futures ----------
def test_futures_open_and_close(demo_token):
    r = requests.post(f"{API}/futures/order", headers=_hdr(demo_token),
                      json={"pair": "BTC/USDT", "side": "long", "leverage": 10, "quantity": 0.001}, timeout=20)
    assert r.status_code == 200, r.text
    pos = r.json()["position"]
    pid = pos["id"]
    r2 = requests.get(f"{API}/futures/positions", headers=_hdr(demo_token), params={"status": "open"}, timeout=15)
    assert r2.status_code == 200
    matching = [p for p in r2.json()["items"] if p["id"] == pid]
    assert matching
    p = matching[0]
    assert "mark_price" in p
    assert "unrealized_pnl" in p
    r3 = requests.post(f"{API}/futures/close", headers=_hdr(demo_token), json={"position_id": pid}, timeout=20)
    assert r3.status_code == 200, r3.text
    assert r3.json().get("ok") is True


# ---------- Earn ----------
def test_earn_subscribe(demo_token):
    r = requests.post(f"{API}/earn/subscribe", headers=_hdr(demo_token),
                      json={"product_id": "p-usdt-flex", "amount": 100}, timeout=15)
    assert r.status_code == 200, r.text
    sub = r.json()["subscription"]
    assert sub["asset"] == "USDT"
    assert sub["amount"] == 100
    # Verify earn balance increased
    bal = requests.get(f"{API}/wallet/balances", headers=_hdr(demo_token), timeout=15).json()["items"]
    usdt = next(w for w in bal if w["asset"] == "USDT")
    assert usdt.get("earn", 0) >= 100


# ---------- KYC ----------
def test_user_kyc_submit_sets_pending():
    # register a fresh user to not disturb demo state
    email = f"kyc_{uuid.uuid4().hex[:8]}@example.com"
    reg = requests.post(f"{API}/auth/register", json={"email": email, "password": "StrongPass!123"}, timeout=20).json()
    tok = reg["access_token"]
    r = requests.post(f"{API}/user/kyc", headers=_hdr(tok),
                      json={"full_name": "Test User", "document_type": "passport",
                            "document_number": "X1234567", "country": "US", "dob": "1990-01-01"}, timeout=15)
    assert r.status_code == 200, r.text
    me = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=15).json()["user"]
    assert me["kyc_status"] == "pending"


# ---------- Admin ----------
def test_admin_dashboard(admin_token):
    r = requests.get(f"{API}/admin/dashboard", headers=_hdr(admin_token), timeout=20)
    assert r.status_code == 200
    data = r.json()
    stats = data["stats"]
    for k in ("total_users", "active_markets", "trades_count"):
        assert k in stats
    assert isinstance(data["activities"], list)
    assert isinstance(data["latest_users"], list)


def test_admin_users_list_and_patch(admin_token):
    r = requests.get(f"{API}/admin/users", headers=_hdr(admin_token), timeout=15)
    assert r.status_code == 200
    users = r.json()["items"]
    assert len(users) >= 1
    # pick demo user and toggle status back and forth
    demo = next(u for u in users if u["email"] == DEMO_EMAIL)
    r2 = requests.patch(f"{API}/admin/users/{demo['id']}", headers=_hdr(admin_token),
                        json={"status": "active"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json()["user"]["status"] == "active"


def test_admin_kyc_decision(admin_token):
    # ensure at least one pending kyc exists (we created one earlier)
    r = requests.get(f"{API}/admin/kyc", headers=_hdr(admin_token), params={"status": "pending"}, timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("No pending KYC to decide (seed may differ)")
    kyc_id = items[0]["id"]
    uid = items[0]["user_id"]
    r2 = requests.post(f"{API}/admin/kyc/{kyc_id}/decision", headers=_hdr(admin_token),
                       json={"decision": "approved"}, timeout=15)
    assert r2.status_code == 200
    # verify user kyc_status approved
    users = requests.get(f"{API}/admin/users", headers=_hdr(admin_token), timeout=15).json()["items"]
    target = next((u for u in users if u["id"] == uid), None)
    assert target and target["kyc_status"] == "approved"


def test_admin_approve_pending_withdrawal(admin_token, demo_token):
    # ensure a pending withdraw exists
    requests.post(f"{API}/wallet/withdraw", headers=_hdr(demo_token),
                  json={"asset": "USDT", "amount": 5, "address": "nxaddr_x", "network": "USDT"}, timeout=15)
    r = requests.get(f"{API}/admin/transactions", headers=_hdr(admin_token),
                     params={"type": "withdraw", "status": "pending"}, timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "no pending withdrawal found"
    tx_id = items[0]["id"]
    r2 = requests.post(f"{API}/admin/transactions/{tx_id}/decision", headers=_hdr(admin_token),
                      json={"decision": "approved"}, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("ok") is True


def test_non_admin_cannot_access_admin(demo_token):
    r = requests.get(f"{API}/admin/dashboard", headers=_hdr(demo_token), timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}"


def test_admin_audit_contains_actions(admin_token):
    r = requests.get(f"{API}/admin/audit", headers=_hdr(admin_token), params={"limit": 200}, timeout=15)
    assert r.status_code == 200
    actions = {row["action"] for row in r.json()["items"]}
    # these should have fired during tests
    assert any(a.startswith("auth.login") for a in actions)
    assert any(a == "trade.order" for a in actions)
    assert any(a.startswith("admin.user.update") for a in actions)

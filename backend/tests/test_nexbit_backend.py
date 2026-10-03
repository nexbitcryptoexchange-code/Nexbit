"""Current NEXBIT backend integration tests.

No demo accounts, demo balances, or hard-coded production credentials are used.
Set NEXBIT_TEST_BASE_URL and the admin credentials in the backend environment when
running the admin/ledger smoke test.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

BASE_URL = os.environ.get("NEXBIT_TEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _register(email: str | None = None):
    email = email or f"e2e_{uuid.uuid4().hex[:12]}@example.com"
    response = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "StrongPass!123", "name": "NEXBIT E2E"},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["access_token"], data["user"]


def _login_admin():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        pytest.skip("ADMIN_EMAIL/ADMIN_PASSWORD are not configured for integration tests")
    response = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user"]["role"] == "admin"
    return data["access_token"]


def test_health():
    response = requests.get(f"{API}/health", timeout=15)
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_register_creates_zero_balances():
    token, user = _register()
    assert user["role"] == "user"
    balances = requests.get(f"{API}/wallet/balances", headers=_headers(token), timeout=20)
    assert balances.status_code == 200, balances.text
    items = balances.json()["items"]
    assert items
    assert all(float(row.get("spot", 0)) == 0.0 for row in items)
    assert all(float(row.get("futures", 0)) == 0.0 for row in items)
    assert all(float(row.get("earn", 0)) == 0.0 for row in items)
    assert all(float(row.get("locked", 0)) == 0.0 for row in items)


def test_user_deposit_cannot_create_balance():
    token, _ = _register()
    response = requests.post(
        f"{API}/wallet/deposit",
        headers=_headers(token),
        json={"asset": "USDT", "amount": 100},
        timeout=15,
    )
    assert response.status_code == 410
    balances = requests.get(f"{API}/wallet/balances", headers=_headers(token), timeout=20)
    usdt = next(row for row in balances.json()["items"] if row["asset"] == "USDT")
    assert float(usdt["spot"]) == 0.0


def test_market_pairs_are_well_formed():
    response = requests.get(f"{API}/market/pairs", timeout=20)
    assert response.status_code == 200, response.text
    pairs = response.json()["items"]
    assert pairs
    assert all(row["symbol"] == f'{row["base"]}/{row["quote"]}' for row in pairs)
    assert all(row["base"] != row["quote"] for row in pairs)
    assert all(isinstance(row["enabled"], bool) for row in pairs)


def test_admin_ledger_credit_is_idempotent_and_debitable():
    admin_token = _login_admin()
    user_token, user = _register()
    reference = f"e2e-{uuid.uuid4().hex}"
    credit = requests.post(
        f"{API}/admin/wallets/adjust",
        headers=_headers(admin_token),
        json={
            "user_id": user["id"],
            "asset": "USDT",
            "amount": 10,
            "action": "credit",
            "reference_id": reference,
            "note": "automated integration test",
        },
        timeout=20,
    )
    assert credit.status_code == 200, credit.text

    duplicate = requests.post(
        f"{API}/admin/wallets/adjust",
        headers=_headers(admin_token),
        json={
            "user_id": user["id"],
            "asset": "USDT",
            "amount": 10,
            "action": "credit",
            "reference_id": reference,
            "note": "duplicate integration request",
        },
        timeout=20,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json().get("duplicate") is True

    balances = requests.get(f"{API}/wallet/balances", headers=_headers(user_token), timeout=20)
    usdt = next(row for row in balances.json()["items"] if row["asset"] == "USDT")
    assert float(usdt["spot"]) == 10.0

    debit = requests.post(
        f"{API}/admin/wallets/adjust",
        headers=_headers(admin_token),
        json={
            "user_id": user["id"],
            "asset": "USDT",
            "amount": 10,
            "action": "debit",
            "reference_id": f"e2e-{uuid.uuid4().hex}",
            "note": "automated integration cleanup",
        },
        timeout=20,
    )
    assert debit.status_code == 200, debit.text

    balances = requests.get(f"{API}/wallet/balances", headers=_headers(user_token), timeout=20)
    usdt = next(row for row in balances.json()["items"] if row["asset"] == "USDT")
    assert float(usdt["spot"]) == 0.0


def test_non_admin_cannot_adjust_balances():
    token, _ = _register()
    response = requests.post(
        f"{API}/admin/wallets/adjust",
        headers=_headers(token),
        json={
            "user_id": "not-authorized",
            "asset": "USDT",
            "amount": 1,
            "action": "credit",
            "reference_id": f"e2e-{uuid.uuid4().hex}",
        },
        timeout=15,
    )
    assert response.status_code == 403


@pytest.mark.skipif(
    os.environ.get("NEXBIT_RUN_REAL_E2E", "").lower() not in {"1", "true", "yes"},
    reason="Set NEXBIT_RUN_REAL_E2E=1 to run the real matching/settlement flow",
)
def test_real_spot_order_requires_funded_accounts():
    admin_token = _login_admin()
    seller_token, seller = _register()
    buyer_token, buyer = _register()

    seller_ref = f"e2e-{uuid.uuid4().hex}"
    buyer_ref = f"e2e-{uuid.uuid4().hex}"
    for user_id, asset, amount, reference in [
        (seller["id"], "BTC", 0.001, seller_ref),
        (buyer["id"], "USDT", 100.0, buyer_ref),
    ]:
        response = requests.post(
            f"{API}/admin/wallets/adjust",
            headers=_headers(admin_token),
            json={
                "user_id": user_id,
                "asset": asset,
                "amount": amount,
                "action": "credit",
                "reference_id": reference,
                "note": "real matching integration test",
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text

    seller_order = requests.post(
        f"{API}/trade/order",
        headers=_headers(seller_token),
        json={
            "pair": "BTC/USDT",
            "side": "sell",
            "type": "limit",
            "quantity": 0.001,
            "price": 50000,
        },
        timeout=20,
    )
    assert seller_order.status_code == 200, seller_order.text

    buyer_order = requests.post(
        f"{API}/trade/order",
        headers=_headers(buyer_token),
        json={
            "pair": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "quantity": 0.001,
        },
        timeout=20,
    )
    assert buyer_order.status_code == 200, buyer_order.text
    assert buyer_order.json()["order"]["status"] == "filled"

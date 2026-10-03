"""BlockBee custody adapter for real crypto deposits and withdrawals.

This module is deliberately fail-closed: without a configured BlockBee V2 API key,
NEXBIT will not create deposit addresses or broadcast withdrawals.
"""
import base64
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class CustodyNotConfigured(RuntimeError):
    pass


class CustodyProviderError(RuntimeError):
    pass


TICKERS = {
    ("BTC", "BTC"): "btc",
    ("ETH", "ETH"): "eth",
    ("USDT", "ERC20"): "erc20_usdt",
    ("USDT", "TRC20"): "trc20_usdt",
    ("USDT", "BEP20"): "bep20_usdt",
    ("USDT", "POLYGON"): "polygon_usdt",
    ("USDC", "ERC20"): "erc20_usdc",
    ("USDC", "BEP20"): "bep20_usdc",
    ("SOL", "SOL"): "sol",
}


def _ticker(asset: str, network: Optional[str]) -> str:
    a = asset.upper()
    n = (network or a).upper().replace("-", "").replace("_", "")
    if a in {"BTC", "ETH", "SOL"} and n == a:
        return TICKERS[(a, a)]
    key = (a, n)
    if key in TICKERS:
        return TICKERS[key]
    raise CustodyProviderError(f"Unsupported custody asset/network: {a}/{network or a}")


def _amount(value: Any) -> str:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CustodyProviderError("Invalid amount")
    if d <= 0:
        raise CustodyProviderError("Amount must be positive")
    return format(d, "f")


class BlockBeeCustody:
    def __init__(self) -> None:
        self.api_key = os.environ.get("BLOCKBEE_API_KEY", "").strip()
        self.base_url = os.environ.get("BLOCKBEE_API_URL", "https://api.blockbee.io").rstrip("/")
        self.public_base_url = os.environ.get("NEXBIT_PUBLIC_BASE_URL", "").rstrip("/")
        self.public_key = os.environ.get("BLOCKBEE_PUBLIC_KEY", "").strip()
        self.timeout = float(os.environ.get("BLOCKBEE_TIMEOUT_SECONDS", "12"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.public_base_url and self.public_key)

    def require_enabled(self) -> None:
        if not self.enabled:
            raise CustodyNotConfigured(
                "BlockBee custody is not configured. Set BLOCKBEE_API_KEY, "
                "BLOCKBEE_PUBLIC_KEY and NEXBIT_PUBLIC_BASE_URL."
            )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        self.require_enabled()
        params = dict(kwargs.pop("params", {}) or {})
        params["apikey"] = self.api_key
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, f"{self.base_url}{path}", params=params, **kwargs)
        try:
            data = response.json()
        except Exception:
            raise CustodyProviderError(f"Custody provider returned HTTP {response.status_code}")
        if response.status_code >= 400 or data.get("status") != "success":
            raise CustodyProviderError(str(data.get("error") or f"Custody provider HTTP {response.status_code}"))
        return data

    async def create_deposit_address(self, user_id: str, asset: str, network: str) -> dict:
        ticker = _ticker(asset, network)
        nonce = os.urandom(18).hex()
        callback = (
            f"{self.public_base_url}/api/webhooks/blockbee/deposit"
            f"?user_id={user_id}&asset={asset.upper()}&network={network.upper()}&nonce={nonce}"
        )
        data = await self._request(
            "GET",
            f"/{ticker}/create/",
            params={
                "callback": callback,
                "post": "1",
                "json": "1",
                "pending": "1",
                "confirmations": os.environ.get("BLOCKBEE_CONFIRMATIONS", "3"),
            },
        )
        return {
            "provider": "blockbee",
            "ticker": ticker,
            "address": data["address_in"],
            "callback_url": data.get("callback_url", callback),
            "minimum_transaction": data.get("minimum_transaction_coin"),
        }

    def validate_asset_network(self, asset: str, network: str) -> str:
        return _ticker(asset, network)

    async def create_withdrawal(self, asset: str, network: str, address: str, amount: Any) -> dict:
        ticker = _ticker(asset, network)
        request_data = await self._request(
            "GET",
            f"/{ticker}/payout/request/create/",
            params={"address": address, "value": _amount(amount)},
        )
        request_id = request_data.get("request_id")
        if not request_id:
            raise CustodyProviderError("Custody provider did not return payout request id")
        payout_data = await self._request(
            "POST",
            "/payout/create/",
            data={"request_ids": request_id},
        )
        info = payout_data.get("payout_info") or {}
        payout_id = info.get("id")
        if not payout_id:
            raise CustodyProviderError("Custody provider did not return payout id")
        process_data = await self._request(
            "POST",
            "/payout/process/",
            data={"payout_id": payout_id},
        )
        return {
            "provider": "blockbee",
            "ticker": ticker,
            "request_id": request_id,
            "payout_id": payout_id,
            "status": (process_data.get("payout_info") or {}).get("status", "processing"),
            "txid": (process_data.get("payout_info") or {}).get("txid") or None,
        }

    async def payout_status(self, payout_id: str) -> dict:
        data = await self._request(
            "POST",
            "/payout/status/",
            data={"payout_id": payout_id},
        )
        return data.get("payout_info") or {}

    async def process_payout(self, payout_id: str) -> dict:
        data = await self._request(
            "POST",
            "/payout/process/",
            data={"payout_id": payout_id},
        )
        return data.get("payout_info") or {}

    def verify_signature(self, payload: bytes, signature_b64: str) -> bool:
        self.require_enabled()
        if not signature_b64:
            return False
        try:
            key = serialization.load_pem_public_key(self.public_key.encode("utf-8"))
            signature = base64.b64decode(signature_b64, validate=True)
            key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False


custody = BlockBeeCustody()

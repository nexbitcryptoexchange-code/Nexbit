"""MongoDB connection and startup helpers."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

client = AsyncIOMotorClient(_mongo_url)
db = client[_db_name]


async def ensure_indexes() -> None:
    await db.users.create_index("email", unique=True)
    await db.users.create_index("role")
    await db.login_attempts.create_index("identifier")
    await db.auth_sessions.create_index("token_hash", unique=True)
    await db.auth_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.auth_sessions.create_index([("user_id", 1), ("revoked", 1)])
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.orders.create_index([("user_id", 1), ("created_at", -1)])
    await db.orders.create_index([("pair", 1), ("status", 1)])
    await db.orders.create_index([("pair", 1), ("side", 1), ("status", 1), ("price", 1), ("created_at", 1)])
    await db.matching_locks.create_index("key", unique=True)
    await db.order_idempotency.create_index([("user_id", 1), ("key", 1)], unique=True)
    await db.transactions.create_index([("user_id", 1), ("created_at", -1)])
    await db.transactions.create_index([("type", 1), ("reference_id", 1)], unique=True, sparse=True)
    await db.positions.create_index([("user_id", 1), ("status", 1)])
    await db.trades.create_index([("pair", 1), ("created_at", -1)])
    await db.trades.create_index("created_at")
    await db.kyc.create_index("user_id", unique=True)
    await db.wallets.create_index([("user_id", 1), ("asset", 1)], unique=True)
    await db.ledger_entries.create_index([("user_id", 1), ("created_at", -1)])
    await db.ledger_entries.create_index("reference_id", sparse=True)
    await db.audit_logs.create_index([("created_at", -1)])
    await db.wallet_addresses.create_index([("user_id", 1), ("asset", 1), ("network", 1)], unique=True)
    await db.wallet_addresses.create_index("address", unique=True)
    await db.blockchain_events.create_index([("provider", 1), ("event_id", 1)], unique=True)
    await db.blockchain_events.create_index([("user_id", 1), ("created_at", -1)])
    await db.payout_events.create_index([("provider", 1), ("event_id", 1), ("status", 1)], unique=True)
    await db.transactions.create_index([("type", 1), ("payout_id", 1)], unique=True, sparse=True)
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])


async def close() -> None:
    client.close()

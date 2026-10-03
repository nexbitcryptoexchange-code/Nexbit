"""One-time financial Decimal128 migration with dry-run and reconciliation safeguards."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from bson.decimal128 import Decimal128

from db import db

COLLECTION_FIELDS = {
    "wallets": ("spot", "futures", "earn", "locked"),
    "ledger_entries": ("delta", "balance_after"),
    "transactions": ("amount",),
    "orders": ("quantity", "price", "stop_price", "filled_qty", "remaining_qty"),
    "trades": ("price", "quantity", "quote_amount", "buyer_fee", "seller_fee"),
    "positions": ("quantity", "entry_price", "margin", "liq_price", "tp", "sl", "pnl", "exit_price"),
    "earn_subs": ("amount", "apy", "earned"),
}
MIGRATION_ID = "financial_decimal128_v1"

def to_decimal128(value):
    if isinstance(value, Decimal128):
        return value
    return Decimal128(Decimal(str(value)))

async def inspect():
    report = {"migration_id": MIGRATION_ID, "collections": {}, "wallet_reconciliation": {}}
    for collection, fields in COLLECTION_FIELDS.items():
        stats = {"documents": 0, "documents_with_legacy_values": 0, "legacy_fields": 0}
        async for doc in db[collection].find({}, {"_id": 1, **{f: 1 for f in fields}}):
            stats["documents"] += 1
            changed = sum(1 for f in fields if doc.get(f) is not None and not isinstance(doc.get(f), Decimal128))
            if changed:
                stats["documents_with_legacy_values"] += 1
                stats["legacy_fields"] += changed
        report["collections"][collection] = stats
    mismatches = []
    async for wallet in db.wallets.find({}, {"_id": 0, "user_id": 1, "asset": 1, "spot": 1, "futures": 1, "earn": 1, "locked": 1}):
        for bucket in ("spot", "futures", "earn", "locked"):
            count = await db.ledger_entries.count_documents({"user_id": wallet.get("user_id"), "asset": wallet.get("asset"), "bucket": bucket})
            if not count:
                continue
            expected = Decimal("0")
            async for entry in db.ledger_entries.find({"user_id": wallet.get("user_id"), "asset": wallet.get("asset"), "bucket": bucket}, {"delta": 1}):
                value = entry.get("delta")
                expected += value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
            actual = wallet.get(bucket)
            actual_d = actual.to_decimal() if isinstance(actual, Decimal128) else Decimal(str(actual))
            if actual_d != expected:
                mismatches.append({"user_id": wallet.get("user_id"), "asset": wallet.get("asset"), "bucket": bucket, "wallet": str(actual_d), "ledger_sum": str(expected)})
    report["wallet_reconciliation"] = {"mismatch_count": len(mismatches), "mismatches": mismatches[:100], "truncated": len(mismatches) > 100}
    return report

async def apply():
    if await db.migrations.find_one({"migration_id": MIGRATION_ID}):
        raise RuntimeError(f"{MIGRATION_ID} has already been applied; refusing a second mutation")
    before = await inspect()
    if before["wallet_reconciliation"]["mismatch_count"]:
        raise RuntimeError("Wallet/ledger reconciliation has mismatches; resolve them before applying")
    changed = 0
    for collection, fields in COLLECTION_FIELDS.items():
        async for doc in db[collection].find({}, {"_id": 1, **{f: 1 for f in fields}}):
            updates = {f: to_decimal128(doc[f]) for f in fields if doc.get(f) is not None and not isinstance(doc.get(f), Decimal128)}
            if updates:
                await db[collection].update_one({"_id": doc["_id"]}, {"$set": updates})
                changed += 1
    after = await inspect()
    if any(v["legacy_fields"] for v in after["collections"].values()) or after["wallet_reconciliation"]["mismatch_count"]:
        raise RuntimeError("Post-migration validation failed; migration marker was not written")
    marker = {
        "migration_id": MIGRATION_ID,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "documents_changed": changed,
        "before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
    }
    await db.migrations.insert_one(marker)
    return marker

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm:
        raise SystemExit("--apply requires --confirm")
    result = await apply() if args.apply else await inspect()
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    asyncio.run(main())

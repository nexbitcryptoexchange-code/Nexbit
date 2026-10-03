"""Exact decimal helpers for financial values.

This module is the single conversion boundary for the upcoming Decimal128
financial migration. It deliberately does not change existing wallet/order
schemas by itself; callers must opt into the helpers at a complete accounting
boundary rather than mixing float and Decimal128 fields.
"""
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128


def to_decimal(value: Any) -> Decimal:
    """Convert a financial value without introducing binary-float artifacts."""
    if isinstance(value, Decimal128):
        result = value.to_decimal()
    elif isinstance(value, Decimal):
        result = value
    else:
        result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("financial value must be finite")
    return result


def to_decimal128(value: Any) -> Decimal128:
    """Convert a financial value to MongoDB Decimal128 exactly."""
    return Decimal128(to_decimal(value))


def decimal_add(left: Any, right: Any) -> Decimal:
    return to_decimal(left) + to_decimal(right)


def decimal_subtract(left: Any, right: Any) -> Decimal:
    return to_decimal(left) - to_decimal(right)


def decimal_multiply(left: Any, right: Any) -> Decimal:
    return to_decimal(left) * to_decimal(right)


def decimal_divide(left: Any, right: Any) -> Decimal:
    divisor = to_decimal(right)
    if divisor == 0:
        raise ZeroDivisionError("cannot divide a financial value by zero")
    return to_decimal(left) / divisor

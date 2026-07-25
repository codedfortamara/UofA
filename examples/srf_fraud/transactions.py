"""Transfer-event schema + edge validation for the SRF fraud demo.

A "transaction" here is an outbound money transfer -- the thing the Shared
Responsibility Framework requires a bank to watch in real time. Validation
mirrors `pipeline/validate.py`: reject malformed transfers at the edge so the
detector only ever scores well-formed data.
"""
from datetime import datetime

REQUIRED_FIELDS = ("txn_id", "account_id", "payee_id", "amount", "timestamp", "currency")
ALLOWED_CURRENCIES = {"SGD", "USD", "EUR", "GBP"}


def validate_transaction(txn):
    """Return a list of error strings; empty means the transfer is well-formed."""
    if not isinstance(txn, dict):
        return ["transaction must be a JSON object"]

    errors = []
    for field in REQUIRED_FIELDS:
        if field not in txn or txn[field] in (None, ""):
            errors.append(f"missing required field: {field}")

    amount = txn.get("amount")
    if amount is not None:
        # bool is a subclass of int -- exclude it explicitly.
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            errors.append("amount must be a number")
        elif amount <= 0:
            errors.append("amount must be > 0")

    currency = txn.get("currency")
    if currency is not None and currency not in ALLOWED_CURRENCIES:
        errors.append(f"unsupported currency {currency!r}")

    timestamp = txn.get("timestamp")
    if timestamp is not None and parse_time(timestamp) is None:
        errors.append(f"timestamp is not ISO-8601: {timestamp!r}")

    return errors


def is_valid(txn):
    return not validate_transaction(txn)


def parse_time(value):
    """Parse an ISO-8601 timestamp (accepting a trailing 'Z'); None if invalid."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

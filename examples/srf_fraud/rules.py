"""The fraud-detection rules -- the heart of the SRF demo.

Each rule is a small, PURE function: given a transaction and that account's prior
transactions (event-time ordered), it returns ``(fired, reason)``. Purity is
deliberate -- rules are the part a compliance team will scrutinise line by line,
so they must be readable and unit-testable in isolation, with no hidden state and
no I/O.

All time reasoning uses EVENT time (the transaction's own ``timestamp``), never
wall-clock processing time. See docs/MOCK_INTERVIEW.md section 6 for why that
distinction matters.
"""
from datetime import timedelta

from examples.srf_fraud.transactions import parse_time


def rapid_drain(txn, history, *, window_minutes=10, max_count=3, max_amount=5000.0):
    """Fire when an account moves many transfers, or a large sum, in a short window.

    This is the direct technical expression of the SRF's core concern:
    "material sums rapidly wiped out" from an account.
    """
    now = parse_time(txn["timestamp"])
    window_start = now - timedelta(minutes=window_minutes)
    recent = [t for t in history if window_start <= parse_time(t["timestamp"]) <= now]
    recent.append(txn)

    count = len(recent)
    total = sum(t["amount"] for t in recent)
    if count >= max_count:
        return True, f"{count} transfers in {window_minutes} min"
    if total > max_amount:
        return True, f"{total:.2f} moved in {window_minutes} min"
    return False, ""


def new_payee_high_value(txn, history, *, amount_threshold=1000.0):
    """Fire on a large transfer to a payee this account has never paid before."""
    known_payees = {t["payee_id"] for t in history}
    if txn["payee_id"] not in known_payees and txn["amount"] >= amount_threshold:
        return True, f"{txn['amount']:.2f} to never-seen payee {txn['payee_id']}"
    return False, ""


def amount_spike(txn, history, *, factor=5.0, min_history=3):
    """Fire when a transfer dwarfs the account's recent typical transfer size."""
    if len(history) < min_history:
        return False, ""  # not enough history to judge "typical"
    mean = sum(t["amount"] for t in history) / len(history)
    if mean > 0 and txn["amount"] > factor * mean:
        return True, f"{txn['amount']:.2f} vs typical {mean:.2f}"
    return False, ""


def odd_hour(txn, history, *, start_hour=2, end_hour=5):
    """Weak signal: a transfer in the small hours. Useful combined with others."""
    when = parse_time(txn["timestamp"])
    if when is not None and start_hour <= when.hour < end_hour:
        return True, f"transfer at {when.hour:02d}:{when.minute:02d}"
    return False, ""


# The ordered rule set the detector applies to every transaction.
RULES = [
    ("rapid_drain", rapid_drain),
    ("new_payee_high_value", new_payee_high_value),
    ("amount_spike", amount_spike),
    ("odd_hour", odd_hour),
]

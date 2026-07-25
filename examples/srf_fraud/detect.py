"""The streaming detector -- the SRF "real-time surveillance" stage.

Reads transactions off the shared `pipeline.stream.Stream` in arrival order,
keeps a small per-account history in memory, scores each transaction against
every rule, and writes alerts + holds to the audit sink.

Once an account has fired *any* alert it is considered "under active drain", so
its subsequent transfers are HELD -- the Protection from Scams Act action. We
keep scoring held transactions too, so the audit trail stays complete (a
regulator wants the full evidence chain, not just the first hit).
"""
from collections import defaultdict

from examples.srf_fraud import alerts as alert_sink
from examples.srf_fraud.rules import RULES
from examples.srf_fraud.transactions import is_valid


def score_transaction(txn, history):
    """Return the list of ``(rule_name, reason)`` that fired for one transaction."""
    fired = []
    for name, rule in RULES:
        ok, reason = rule(txn, history)
        if ok:
            fired.append((name, reason))
    return fired


def run(stream, conn):
    """Drain the stream, score every transaction, persist alerts + holds.

    Returns a summary dict (used by the demo and the tests).
    """
    history = defaultdict(list)
    flagged = set()  # accounts under an active alert -> hold their transfers
    summary = {"processed": 0, "skipped": 0, "alerts": [], "holds": []}

    for _offset, txn in stream.read():
        if not is_valid(txn):
            summary["skipped"] += 1
            continue
        summary["processed"] += 1
        account = txn["account_id"]
        was_flagged = account in flagged

        for name, reason in score_transaction(txn, history[account]):
            alert_sink.record_alert(
                conn, txn_id=txn["txn_id"], account_id=account,
                rule=name, reason=reason, timestamp=txn["timestamp"],
            )
            summary["alerts"].append(
                {"txn_id": txn["txn_id"], "rule": name, "reason": reason}
            )
            flagged.add(account)

        if was_flagged:
            reason = "account under active drain alert"
            alert_sink.record_hold(
                conn, txn_id=txn["txn_id"], account_id=account,
                timestamp=txn["timestamp"], reason=reason,
            )
            summary["holds"].append({"txn_id": txn["txn_id"], "reason": reason})

        history[account].append(txn)

    return summary

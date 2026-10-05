"""Unit tests for the fraud rules, plus an end-to-end detector test.

The rules are the part a compliance team argues about, so they get the hardest,
most explicit tests -- one behaviour per test, against a tiny labelled dataset.
"""
from examples.srf_fraud import alerts, detect
from examples.srf_fraud.rules import (
    amount_spike,
    new_payee_high_value,
    odd_hour,
    rapid_drain,
)
from pipeline.stream import Stream


def txn(txn_id, account="acc", payee="p", amount=10.0, ts="2026-07-25T12:00:00Z"):
    return {
        "txn_id": txn_id,
        "account_id": account,
        "payee_id": payee,
        "amount": amount,
        "currency": "SGD",
        "timestamp": ts,
    }


# --- rapid_drain -------------------------------------------------------------

def test_rapid_drain_fires_on_count_in_window():
    history = [
        txn("a", ts="2026-07-25T03:01:00Z", amount=100),
        txn("b", ts="2026-07-25T03:02:00Z", amount=100),
    ]
    fired, _ = rapid_drain(txn("c", ts="2026-07-25T03:03:00Z", amount=100), history)
    assert fired  # three transfers inside 10 minutes


def test_rapid_drain_ignores_old_transfers():
    history = [
        txn("a", ts="2026-07-20T03:01:00Z", amount=100),
        txn("b", ts="2026-07-21T03:02:00Z", amount=100),
    ]
    fired, _ = rapid_drain(txn("c", ts="2026-07-25T03:03:00Z", amount=100), history)
    assert not fired  # days apart -> not "rapid"


def test_rapid_drain_fires_on_large_sum():
    fired, _ = rapid_drain(txn("c", amount=6000, ts="2026-07-25T03:00:00Z"), [])
    assert fired


# --- new_payee_high_value ----------------------------------------------------

def test_new_payee_high_value_fires():
    history = [txn("a", payee="known", amount=50)]
    fired, _ = new_payee_high_value(txn("c", payee="stranger", amount=2000), history)
    assert fired


def test_new_payee_low_value_does_not_fire():
    fired, _ = new_payee_high_value(txn("c", payee="stranger", amount=20), [])
    assert not fired


def test_known_payee_high_value_does_not_fire():
    history = [txn("a", payee="landlord", amount=800)]
    fired, _ = new_payee_high_value(txn("c", payee="landlord", amount=2000), history)
    assert not fired


# --- amount_spike ------------------------------------------------------------

def test_amount_spike_needs_enough_history():
    fired, _ = amount_spike(txn("c", amount=10000), [])
    assert not fired


def test_amount_spike_fires_on_outlier():
    history = [txn(str(i), amount=20) for i in range(3)]
    fired, _ = amount_spike(txn("c", amount=1000), history)
    assert fired


# --- odd_hour ----------------------------------------------------------------

def test_odd_hour_fires_in_small_hours():
    assert odd_hour(txn("c", ts="2026-07-25T03:30:00Z"), [])[0]


def test_odd_hour_quiet_in_daytime():
    assert not odd_hour(txn("c", ts="2026-07-25T13:30:00Z"), [])[0]


# --- end-to-end detector -----------------------------------------------------

def test_detector_alerts_on_drain_and_holds_followups(tmp_path):
    stream = Stream(tmp_path / "s.jsonl")
    # normal history for the victim account
    stream.put(txn("t1", account="v", payee="grocer", amount=25, ts="2026-07-20T12:00:00Z"))
    stream.put(txn("t2", account="v", payee="grocer", amount=30, ts="2026-07-22T12:00:00Z"))
    stream.put(txn("t3", account="v", payee="grocer", amount=40, ts="2026-07-24T12:00:00Z"))
    # the phishing drain: new payee, small hours, escalating amounts
    stream.put(txn("t4", account="v", payee="mule", amount=1500, ts="2026-07-25T03:01:00Z"))
    stream.put(txn("t5", account="v", payee="mule", amount=2000, ts="2026-07-25T03:03:00Z"))

    conn = alerts.connect()
    summary = detect.run(stream, conn)

    assert summary["processed"] == 5
    assert any(a["txn_id"] == "t4" for a in summary["alerts"])  # drain detected
    assert any(h["txn_id"] == "t5" for h in summary["holds"])   # follow-up held


def test_detector_skips_malformed_transactions(tmp_path):
    stream = Stream(tmp_path / "s.jsonl")
    stream.put(txn("ok", amount=10))
    stream.put({"txn_id": "bad"})  # missing required fields
    conn = alerts.connect()
    summary = detect.run(stream, conn)
    assert summary["processed"] == 1 and summary["skipped"] == 1

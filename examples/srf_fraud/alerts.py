"""Alert + hold sink -- the auditable record that surveillance actually ran.

Every alert is stored with the rule that fired, a human-readable reason, and the
transaction's timestamp. This table *is* the audit trail a regulator asks for
after an incident: proof of what the bank saw and when. Writes are idempotent on
``(txn_id, rule)`` so replaying the stream can never inflate the record -- the
same at-least-once discipline as `pipeline/persist.py`.
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    txn_id     TEXT NOT NULL,
    account_id TEXT NOT NULL,
    rule       TEXT NOT NULL,
    reason     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    PRIMARY KEY (txn_id, rule)
);
CREATE TABLE IF NOT EXISTS holds (
    txn_id     TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    reason     TEXT NOT NULL
);
"""


def connect(db_path=":memory:"):
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def record_alert(conn, *, txn_id, account_id, rule, reason, timestamp):
    conn.execute(
        "INSERT OR IGNORE INTO alerts VALUES (?, ?, ?, ?, ?)",
        (txn_id, account_id, rule, reason, timestamp),
    )
    conn.commit()


def record_hold(conn, *, txn_id, account_id, timestamp, reason):
    conn.execute(
        "INSERT OR IGNORE INTO holds VALUES (?, ?, ?, ?)",
        (txn_id, account_id, timestamp, reason),
    )
    conn.commit()


def alert_count(conn):
    return conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]


def hold_count(conn):
    return conn.execute("SELECT COUNT(*) FROM holds").fetchone()[0]

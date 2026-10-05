"""Persistence stage -- the local stand-in for Kinesis Firehose writing to S3,
made queryable the way Athena makes S3 queryable.

We use SQLite because it is an entire "data warehouse + query engine" in a
single standard-library module: no server, no setup, just a file on disk.

Firehose's defining behaviour is *batching*: it buffers records and flushes them
in chunks to cut the number of expensive writes. ``persist_batch`` imitates that,
and ``drain_stream`` reads the stream in ``BATCH_SIZE`` chunks.
"""
import sqlite3
from pathlib import Path

from .config import BATCH_SIZE, DB_PATH
from .validate import is_valid

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    value      REAL
);
"""


def connect(db_path=DB_PATH):
    """Open (creating if needed) the warehouse and ensure the schema exists."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def persist_batch(conn, records):
    """Insert a batch of records. Returns the number of rows written.

    We use ``INSERT OR IGNORE`` so replaying the same event twice does not create
    a duplicate row -- a cheap form of idempotency keyed on ``event_id``. Real
    pipelines obsess over this because streams deliver "at least once", meaning
    duplicates are normal and your persistence layer must tolerate them.
    """
    rows = [
        (r["event_id"], r["user_id"], r["event_type"], r["timestamp"], r.get("value"))
        for r in records
    ]
    cur = conn.executemany(
        "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)", rows
    )
    conn.commit()
    return cur.rowcount


def drain_stream(stream, conn, batch_size=BATCH_SIZE):
    """Read valid records off the stream and persist them in batches.

    Returns ``(written, skipped)``. Invalid records are skipped defensively even
    though ingestion already validated them -- defence in depth: never assume an
    upstream stage did its job perfectly.
    """
    written = skipped = 0
    batch = []
    for _offset, record in stream.read():
        if not is_valid(record):
            skipped += 1
            continue
        batch.append(record)
        if len(batch) >= batch_size:
            written += persist_batch(conn, batch)
            batch = []
    if batch:  # flush the final partial batch
        written += persist_batch(conn, batch)
    return written, skipped

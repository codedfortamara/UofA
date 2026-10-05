"""Tests for the persistence (Firehose -> S3) stage."""
from pipeline.persist import connect, drain_stream, persist_batch
from pipeline.stream import Stream


def ev(i, event_type="click"):
    return {
        "event_id": f"e{i}",
        "user_id": "u1",
        "event_type": event_type,
        "timestamp": "2026-07-25T10:00:00Z",
        "value": 1,
    }


def test_persist_batch_writes_rows(tmp_path):
    conn = connect(tmp_path / "w.db")
    assert persist_batch(conn, [ev(1), ev(2)]) == 2


def test_persist_is_idempotent_on_event_id(tmp_path):
    # Streams deliver "at least once", so replays must not create duplicates.
    conn = connect(tmp_path / "w.db")
    persist_batch(conn, [ev(1)])
    persist_batch(conn, [ev(1)])
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_drain_stream_skips_invalid_records(tmp_path):
    s = Stream(tmp_path / "s.jsonl")
    s.put(ev(1))
    s.put({"event_id": "bad"})  # invalid: missing fields
    conn = connect(tmp_path / "w.db")
    written, skipped = drain_stream(s, conn, batch_size=2)
    assert (written, skipped) == (1, 1)

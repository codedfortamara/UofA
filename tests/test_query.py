"""Tests for the query/analytics (Athena) stage."""
from pipeline import query
from pipeline.persist import connect, persist_batch


def seed(conn):
    persist_batch(
        conn,
        [
            {"event_id": "1", "user_id": "a", "event_type": "click", "timestamp": "2026-07-25T10:00:00Z", "value": 0},
            {"event_id": "2", "user_id": "a", "event_type": "purchase", "timestamp": "2026-07-25T10:01:00Z", "value": 10},
            {"event_id": "3", "user_id": "b", "event_type": "purchase", "timestamp": "2026-07-25T10:02:00Z", "value": 5},
        ],
    )


def test_event_count(tmp_path):
    conn = connect(tmp_path / "w.db")
    seed(conn)
    assert query.event_count(conn) == 3


def test_count_by_event_type(tmp_path):
    conn = connect(tmp_path / "w.db")
    seed(conn)
    counts = {r["event_type"]: r["count"] for r in query.count_by_event_type(conn)}
    assert counts == {"purchase": 2, "click": 1}


def test_top_users(tmp_path):
    conn = connect(tmp_path / "w.db")
    seed(conn)
    assert query.top_users(conn, limit=1)[0] == {"user_id": "a", "count": 2}


def test_total_purchase_value(tmp_path):
    conn = connect(tmp_path / "w.db")
    seed(conn)
    assert query.total_purchase_value(conn) == 15

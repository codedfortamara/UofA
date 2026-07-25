"""Query / analytics stage -- the local stand-in for Amazon Athena.

Athena runs SQL over data sitting in S3. Here we run SQL over the same SQLite
file the persistence stage wrote. The lesson worth internalising: "analytics" is
not a magic service, it is just SQL (or something SQL-like) over your persisted
data. Keeping these queries in version-controlled code -- rather than typing them
into a web console -- is the book's "never use the web console" advice applied to
reads as well as writes.
"""


def event_count(conn):
    return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def count_by_event_type(conn):
    cur = conn.execute(
        "SELECT event_type, COUNT(*) AS n "
        "FROM events GROUP BY event_type ORDER BY n DESC, event_type"
    )
    return [{"event_type": row[0], "count": row[1]} for row in cur.fetchall()]


def top_users(conn, limit=5):
    cur = conn.execute(
        "SELECT user_id, COUNT(*) AS n "
        "FROM events GROUP BY user_id ORDER BY n DESC, user_id LIMIT ?",
        (limit,),
    )
    return [{"user_id": row[0], "count": row[1]} for row in cur.fetchall()]


def total_purchase_value(conn):
    cur = conn.execute(
        "SELECT COALESCE(SUM(value), 0) FROM events WHERE event_type = 'purchase'"
    )
    return cur.fetchone()[0]

#!/usr/bin/env python3
"""End-to-end runner for the mini data pipeline.

Usage:
    python run_pipeline.py batch    # push the sample dataset through every stage
    python run_pipeline.py serve    # start the ingestion HTTP API on :8000
    python run_pipeline.py query    # print analytics over whatever is persisted

`batch` mode is the fastest way to watch the whole architecture work end to end:

    sample file -> validate -> stream -> persist -> query
"""
import json
import sys

from pipeline import config, query
from pipeline.persist import connect, drain_stream
from pipeline.stream import Stream
from pipeline.validate import validate_event


def run_batch():
    stream = Stream()
    stream.clear()  # start from an empty log so the demo is repeatable

    accepted = rejected = 0
    with config.SAMPLE_EVENTS.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if validate_event(event):  # non-empty error list -> reject at edge
                rejected += 1
                continue
            stream.put(event)
            accepted += 1
    print(f"ingest:  {accepted} accepted, {rejected} rejected at the edge")

    conn = connect()
    conn.execute("DELETE FROM events")  # repeatable demo
    written, skipped = drain_stream(stream, conn)
    print(f"persist: {written} written, {skipped} skipped")
    _print_analytics(conn)


def run_query():
    _print_analytics(connect())


def _print_analytics(conn):
    print("\n--- analytics (Athena-style SQL) ---")
    print("total events:         ", query.event_count(conn))
    print("events by type:       ", query.count_by_event_type(conn))
    print("top users:            ", query.top_users(conn))
    print("total purchase value: ", query.total_purchase_value(conn))


def main(argv):
    command = argv[1] if len(argv) > 1 else "batch"
    if command == "batch":
        run_batch()
    elif command == "serve":
        from pipeline.ingest import serve

        serve()
    elif command == "query":
        run_query()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

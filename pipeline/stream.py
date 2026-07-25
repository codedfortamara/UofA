"""Streaming stage -- the local stand-in for a Kinesis Data Stream.

A stream is an append-only, ordered log of records. Producers ``put`` records
onto the end; consumers ``read`` from an offset and move forward. This decouples
ingestion speed from processing speed: a burst of traffic piles up harmlessly in
the log instead of overwhelming the database. That buffering is the entire
reason Kinesis / Kafka / Pub-Sub exist in a real pipeline.

We back the stream with a JSONL file so it survives process restarts and can be
inspected by eye. The book's advice to "prefer text formats" applies to your
operational plumbing, not just your datasets.
"""
import json
from pathlib import Path

from .config import STREAM_PATH


class Stream:
    def __init__(self, path=STREAM_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def put(self, record):
        """Append one record to the end of the log. Returns its offset."""
        offset = self.size()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return offset

    def read(self, from_offset=0):
        """Yield ``(offset, record)`` pairs starting at ``from_offset``.

        Reading never removes records -- exactly like Kinesis, consumers track
        their own position. That is what makes replay and multiple independent
        consumers possible: the log is the source of truth, the offset is just a
        bookmark.
        """
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for offset, line in enumerate(fh):
                if offset < from_offset:
                    continue
                line = line.strip()
                if line:
                    yield offset, json.loads(line)

    def size(self):
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def clear(self):
        if self.path.exists():
            self.path.unlink()

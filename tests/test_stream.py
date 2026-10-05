"""Tests for the streaming (Kinesis) stage."""
from pipeline.stream import Stream


def test_put_and_read_roundtrip(tmp_path):
    s = Stream(tmp_path / "s.jsonl")
    s.put({"a": 1})
    s.put({"a": 2})
    assert [r for _o, r in s.read()] == [{"a": 1}, {"a": 2}]


def test_offsets_are_sequential(tmp_path):
    s = Stream(tmp_path / "s.jsonl")
    assert s.put({"a": 1}) == 0
    assert s.put({"a": 2}) == 1


def test_read_from_offset(tmp_path):
    s = Stream(tmp_path / "s.jsonl")
    for i in range(3):
        s.put({"i": i})
    assert [r for _o, r in s.read(from_offset=1)] == [{"i": 1}, {"i": 2}]


def test_reading_does_not_consume(tmp_path):
    # A stream is a log, not a queue: reading it twice yields the same records.
    s = Stream(tmp_path / "s.jsonl")
    s.put({"a": 1})
    list(s.read())
    list(s.read())
    assert s.size() == 1

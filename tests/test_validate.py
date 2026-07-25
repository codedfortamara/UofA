"""Tests for the validation (edge Lambda) stage."""
from pipeline.validate import is_valid, validate_event

VALID = {
    "event_id": "e1",
    "user_id": "u1",
    "event_type": "click",
    "timestamp": "2026-07-25T10:00:00Z",
    "value": 2,
}


def test_valid_event_has_no_errors():
    assert validate_event(VALID) == []
    assert is_valid(VALID)


def test_missing_required_field_is_reported():
    bad = dict(VALID)
    del bad["user_id"]
    assert any("user_id" in e for e in validate_event(bad))


def test_unknown_event_type_is_rejected():
    bad = dict(VALID, event_type="explode")
    assert any("event_type" in e for e in validate_event(bad))


def test_bad_timestamp_is_rejected():
    bad = dict(VALID, timestamp="last tuesday")
    assert any("timestamp" in e for e in validate_event(bad))


def test_negative_value_is_rejected():
    bad = dict(VALID, value=-1)
    assert any("value" in e for e in validate_event(bad))


def test_boolean_is_not_a_valid_number():
    # bool is a subclass of int in Python -- a classic footgun this guards against.
    bad = dict(VALID, value=True)
    assert any("value" in e for e in validate_event(bad))


def test_non_dict_payload_is_rejected():
    assert validate_event("not a dict")
    assert validate_event(None)

"""Validation stage -- the local stand-in for the AWS Lambda that sits behind
API Gateway and rejects malformed events before they enter the pipeline.

Why validate at the edge? A pipeline is only as trustworthy as the data it
lets in. Catching bad records at the front door keeps the downstream stream,
warehouse, and analytics clean. "Garbage in, garbage out" is a data pipeline's
most common and most expensive failure mode, and it is far cheaper to reject a
bad record now than to hunt it down in a dashboard three weeks later.
"""
from datetime import datetime

from .config import ALLOWED_EVENT_TYPES

REQUIRED_FIELDS = ("event_id", "user_id", "event_type", "timestamp")


def validate_event(event):
    """Return a list of human-readable error strings.

    An empty list means the event is valid. We deliberately collect *all*
    errors instead of raising on the first one, so a caller (or a human
    debugging a rejected payload) sees the complete picture in one pass.
    """
    if not isinstance(event, dict):
        return ["event must be a JSON object"]

    errors = []

    for field in REQUIRED_FIELDS:
        if field not in event or event[field] in (None, ""):
            errors.append(f"missing required field: {field}")

    event_type = event.get("event_type")
    if event_type is not None and event_type not in ALLOWED_EVENT_TYPES:
        errors.append(
            f"invalid event_type {event_type!r}; "
            f"allowed: {sorted(ALLOWED_EVENT_TYPES)}"
        )

    timestamp = event.get("timestamp")
    if timestamp is not None and not _is_iso8601(timestamp):
        errors.append(f"timestamp is not ISO-8601: {timestamp!r}")

    # `value` is optional, but if present it must be a non-negative number.
    if event.get("value") is not None:
        value = event["value"]
        # bool is a subclass of int in Python, so exclude it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append("value must be a number")
        elif value < 0:
            errors.append("value must be >= 0")

    return errors


def is_valid(event):
    """Convenience boolean wrapper around ``validate_event``."""
    return not validate_event(event)


def _is_iso8601(value):
    if not isinstance(value, str):
        return False
    try:
        # Accept a trailing 'Z' (UTC), which older fromisoformat() rejected.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

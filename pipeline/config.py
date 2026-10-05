"""Central configuration for the pipeline.

Pulling paths and tunables into one module -- instead of scattering string
literals across the codebase -- is a small but real infrastructure lesson:
*configuration is the seam between your code and the environment it runs in.*

In AWS this same role is played by environment variables, SSM Parameter Store,
or Terraform input variables. Keeping it in one place is what lets you point
the same code at a laptop, a CI runner, or production without editing logic.
"""
from pathlib import Path

# Project root = the directory that contains the `pipeline` package.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# The stream log -- our local stand-in for a Kinesis Data Stream.
STREAM_PATH = DATA_DIR / "stream.jsonl"

# The warehouse -- our local stand-in for S3 + Athena, backed by SQLite.
DB_PATH = DATA_DIR / "warehouse.db"

# A small, version-controlled sample dataset used by the runner and tests.
SAMPLE_EVENTS = DATA_DIR / "sample_events.jsonl"

# Business rule: the only event types the pipeline accepts.
ALLOWED_EVENT_TYPES = {"page_view", "click", "purchase", "signup"}

# Firehose-style batching: how many records to accumulate before a flush.
BATCH_SIZE = 5

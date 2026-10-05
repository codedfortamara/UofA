# Architecture & trade-offs

This document explains *why* the pipeline is shaped the way it is, and — the
part interviewers care about most — **how each stage would change when it has to
handle real scale.** The local version is deliberately the simplest thing that
demonstrates each concept; knowing the "grown-up" version of each is what turns
a demo into an interview answer.

## The pattern: a staged pipeline

```
ingest → stream → persist → query
```

Every stage does one job and hands off to the next through a simple interface.
This is the single most important structural idea in data engineering, because
it lets each stage **scale, fail, and be replaced independently.**

## Stage 1 — Ingest (`pipeline/ingest.py`)

- **Job:** accept events over HTTP, validate, reject the bad ones.
- **Why validate here:** the cheapest place to catch bad data is the front door.
  A bad record that gets in must otherwise be found and fixed downstream, often
  after it has already corrupted a dashboard or a model.
- **Local simplification:** a single-process `http.server`.
- **At real scale:** API Gateway (managed, autoscaling, auth, rate-limiting) in
  front of a Lambda that runs the validation. You stop caring about servers.
- **Failure mode to name in an interview:** if validation is too strict you drop
  good data; too loose and you poison the pipeline. Version your schema.

## Stage 2 — Stream (`pipeline/stream.py`)

- **Job:** an append-only, ordered, replayable log that buffers events.
- **Why a log and not a direct DB write:** it **decouples** producer speed from
  consumer speed. A traffic spike accumulates in the log instead of overwhelming
  the database. Multiple independent consumers can each read at their own pace.
- **Key property — offsets:** consumers track *their own* position; reading
  doesn't delete anything. That's what makes **replay** possible (reprocess
  history after a bug fix) and lets you add new consumers later.
- **Local simplification:** one JSONL file, single "shard".
- **At real scale:** Kinesis or Kafka with many shards/partitions for
  parallelism, a retention window, and consumer groups.
- **Delivery semantics:** real streams are **at-least-once** — you *will* see
  duplicates. That single fact dictates the next stage's design.

## Stage 3 — Persist (`pipeline/persist.py`)

- **Job:** durably store events for later analysis.
- **Batching:** we flush in chunks (`BATCH_SIZE`) instead of one row at a time.
  Fewer, larger writes are dramatically cheaper — this is exactly what Kinesis
  Firehose does before it drops files into S3.
- **Idempotency:** `INSERT OR IGNORE` keyed on `event_id` means processing the
  same event twice is harmless. Because the stream is at-least-once, **the
  persistence layer must be idempotent or your counts will be wrong.** This is
  the highest-value sentence in this whole document for an interview.
- **Local simplification:** SQLite (a warehouse + query engine in one file).
- **At real scale:** Firehose → partitioned Parquet in S3; query with Athena, or
  load into Redshift/Snowflake/BigQuery.

## Stage 4 — Query (`pipeline/query.py`)

- **Job:** answer analytical questions over the persisted data.
- **The lesson:** "analytics" is not a special product — it's SQL over your
  storage. Athena is "SQL over S3"; here it's "SQL over SQLite".
- **Why in code, not a console:** version-controlled queries are reviewable,
  testable, and reproducible. Typing SQL into a console is the read-side version
  of the anti-pattern the book warns against.

## Cross-cutting concerns (the "senior" answers)

- **Schema evolution:** events change over time. Prefer additive changes; keep
  old fields optional; version the schema so old and new events coexist.
- **Idempotency & exactly-once:** true exactly-once is expensive and often
  faked with at-least-once delivery + idempotent writes (what we do here).
- **Backpressure:** when a consumer falls behind, the log absorbs the slack.
  Monitoring *consumer lag* (how far behind the newest offset a consumer is) is
  how you detect trouble before users do.
- **Observability:** counts at each stage (accepted / rejected / written /
  skipped — which this pipeline prints) are the minimum viable metrics. Real
  systems add latency, lag, and error-rate dashboards + alerts.
- **Cost:** batching, compression, and columnar formats (Parquet) exist mostly
  to cut cost at scale. "Why Parquet?" → columnar + compressed → you scan less
  data → Athena/BigQuery charge you less.
```

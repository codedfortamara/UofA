# Mini Data Pipeline — an FDE interview primer

A tiny, **zero-dependency**, fully runnable data pipeline that mirrors a classic
AWS architecture on your laptop, built to teach the fundamentals a **Forward
Deployed Engineer (FDE)** is expected to know cold: ingestion, streaming,
persistence, analytics, infrastructure-as-code, testing, and CI/CD.

It is a working model of the architecture described in two data-engineering book
chapters — *"Automate Your Infrastructure"* and *"Automate the Data Pipeline"* —
shrunk down so you can read every line in an afternoon and explain it in an
interview.

```
      HTTP POST                                                     SQL
  ┌──────────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌───────┐
  │   ingest     │──▶│  stream  │──▶│ persist  │──▶│ warehouse │◀──│ query │
  │ validate at  │   │ append-  │   │ batched  │   │  (SQLite) │   │  SQL  │
  │  the edge    │   │ only log │   │  writes  │   │           │   │       │
  └──────────────┘   └──────────┘   └──────────┘   └───────────┘   └───────┘
   API Gateway        Kinesis        Firehose          S3            Athena
    + Lambda        Data Streams     -> S3
```

## The one-to-one mapping to AWS

Every local module is a stand-in for one real AWS service. Learn the small
version here and you understand the big version.

| Local file            | AWS service              | What it teaches                          |
| --------------------- | ------------------------ | ---------------------------------------- |
| `pipeline/ingest.py`  | API Gateway + Lambda     | Ingestion & **validation at the edge**   |
| `pipeline/stream.py`  | Kinesis Data Streams     | **Buffering**, offsets, replay           |
| `pipeline/persist.py` | Kinesis Firehose → S3    | **Batching** & **idempotency**           |
| `pipeline/query.py`   | Amazon Athena            | Analytics = **SQL over stored data**     |
| `infra/main.tf`       | Terraform / CloudFormation | **Infrastructure as code**             |
| `.github/workflows/`  | Any CI/CD system         | **Automated test-before-ship**           |

## Quick start (works on a phone shell, a laptop, or CI)

```bash
# 1. Run the whole pipeline over the sample dataset:
python run_pipeline.py batch

# 2. Or run the ingestion API and POST your own events:
python run_pipeline.py serve
#   then, from another shell:
curl -X POST localhost:8000/events -d \
  '{"event_id":"x1","user_id":"me","event_type":"click","timestamp":"2026-07-25T10:00:00Z"}'

# 3. Run the tests:
pip install -r requirements-dev.txt
python -m pytest
```

`make run`, `make test`, `make serve`, and `make query` are shortcuts for the same.

### What `batch` prints, and why

```
ingest:  8 accepted, 2 rejected at the edge
persist: 8 written, 0 skipped
...
```

The sample dataset has **10 events, 2 of them deliberately broken** (one has an
unknown `event_type`, one has a malformed `timestamp`). They are rejected at
ingestion and never pollute the warehouse — that is the whole point of
validating at the edge.

## How data flows, stage by stage

1. **Ingest** (`ingest.py`) — an HTTP endpoint accepts a JSON event, validates
   it, and rejects anything malformed with a `400` and a list of reasons. Only
   clean data proceeds.
2. **Stream** (`stream.py`) — accepted events are appended to an ordered log.
   The log **decouples** the fast front door from the slower database: traffic
   spikes pile up in the log instead of crashing the writer.
3. **Persist** (`persist.py`) — a consumer reads the log in **batches** and
   writes them to the warehouse, using `INSERT OR IGNORE` so replayed events
   don't create duplicates (**idempotency**).
4. **Query** (`query.py`) — analytics are plain SQL over the warehouse, kept in
   version-controlled code rather than typed into a console.

## The two big ideas from the book

**1. Automate your infrastructure.** Don't click services together in a web
console. Describe them as code (`infra/main.tf`), keep that code in version
control, review changes as pull requests, and let a tool apply them. This is
repeatable, reviewable, and safe. See [`infra/README.md`](infra/README.md).

**2. Automate the pipeline itself.** Treat pipeline code like real software:
small testable modules, a small committed sample dataset, text formats that
diff cleanly, and a CI/CD pipeline that runs the tests on every change. See
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Where to go next

- 📐 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the design, the trade-offs,
  and how you'd scale each stage for real.
- 🎯 [`docs/FDE_INTERVIEW_GUIDE.md`](docs/FDE_INTERVIEW_GUIDE.md) — the concepts,
  the vocabulary, and the questions an FDE interview will actually ask, each
  answered by pointing at code in this repo.
- 🔥 [`docs/MOCK_INTERVIEW.md`](docs/MOCK_INTERVIEW.md) — harder open-ended
  scenarios (schema migration, backfills, consumer lag, poison messages,
  event-time vs processing-time, exactly-once) with a self-drill checklist.

## Project layout

```
pipeline/        the five pipeline stages (one file each)
tests/           a pytest suite, one file per stage
data/            the committed sample dataset (+ generated output, git-ignored)
infra/           Terraform IaC describing the AWS equivalent (teaching)
docs/            architecture notes and the FDE interview guide
run_pipeline.py  the end-to-end runner (batch / serve / query)
.github/         the CI/CD pipeline
```

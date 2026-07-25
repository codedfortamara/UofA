# The FDE Interview Guide

A **Forward Deployed Engineer** sits between a customer and a product: you build
real, working software *at the customer's site*, with their data and their
constraints, and you have to explain what you built to non-experts. Interviews
therefore test three things at once:

1. **Can you build an end-to-end system?** (not just an algorithm)
2. **Do you understand the trade-offs?** (why this, not that)
3. **Can you explain it clearly?** (teach it back)

This repo is a compact prop for all three. Everything below is answerable by
pointing at code in this project. Read it, run it, then practise saying each
answer out loud.

---

## Part 1 — The vocabulary (know these cold)

| Term | One-sentence definition | Where it lives here |
| --- | --- | --- |
| **Pipeline** | A series of stages that each transform data and hand off to the next. | the whole `pipeline/` package |
| **Ingestion** | Getting data *into* the system from the outside world. | `ingest.py` |
| **Validation at the edge** | Rejecting bad data at the entry point, before it spreads. | `validate.py` |
| **Stream / log** | An append-only, ordered, replayable sequence of records. | `stream.py` |
| **Offset** | A consumer's bookmark into the stream; reading doesn't delete. | `Stream.read()` |
| **Buffering / decoupling** | Letting a fast producer and slow consumer run at different speeds. | why `stream.py` exists |
| **Batching** | Writing many records at once instead of one at a time, for efficiency. | `persist_batch()` |
| **Idempotency** | Doing the same operation twice has the same effect as doing it once. | `INSERT OR IGNORE` in `persist.py` |
| **At-least-once delivery** | The stream may deliver duplicates; consumers must cope. | motivates idempotency |
| **Persistence** | Durable storage of data for later use. | SQLite warehouse |
| **Infrastructure as Code (IaC)** | Declaring your infrastructure in version-controlled files. | `infra/main.tf` |
| **CI/CD** | Automatically testing (and shipping) every change. | `.github/workflows/ci.yml` |
| **Idempotent + IaC** | `terraform apply` converges to the declared state no matter the starting point. | `infra/README.md` |

If you can define every row without looking, you're ahead of most candidates.

---

## Part 2 — The concepts, explained

### 2.1 Why a *pipeline* (staged) instead of one big script?

Because each stage can **scale, fail, and be replaced independently.** If
ingestion gets 10x traffic you scale only ingestion. If the database is slow,
the stream absorbs the backlog and nothing upstream breaks. A monolithic script
has no such seams — one slow part stalls everything.

> **Say this:** "I split it into stages so each has one responsibility and a
> clean handoff, which lets me scale and debug them independently."

### 2.2 Why validate at the edge?

Bad data is cheapest to kill at the front door. Let it in and you'll spend days
later hunting a wrong number in a dashboard back to a malformed record. In this
repo, `sample_events.jsonl` contains two broken events; run `python
run_pipeline.py batch` and watch them get rejected before they ever reach the
warehouse.

> **Say this:** "Garbage in, garbage out. I validate at ingestion so the rest of
> the pipeline can trust its input."

### 2.3 Why a stream/log in the middle?

Two reasons: **decoupling** and **replay.**
- *Decoupling:* the HTTP front door can accept a burst of events instantly;
  they queue in the log and drain into the DB at whatever rate the DB can take.
- *Replay:* because reading uses an offset and never deletes, you can reprocess
  history — e.g. after fixing a bug in the persistence logic — just by reading
  from offset 0 again.

> **Say this:** "The log decouples producers from consumers and gives me replay,
> because consumers track their own offset and reads are non-destructive."

### 2.4 The idempotency question (the one they're really asking)

Real streams deliver **at least once**, so duplicates are normal. If your writer
isn't idempotent, duplicates inflate every count. Here, `persist_batch` uses
`INSERT OR IGNORE` keyed on `event_id`: replay the same event and the row count
doesn't change. `tests/test_persist.py::test_persist_is_idempotent_on_event_id`
proves it.

> **Say this:** "Streams are at-least-once, so I made the write idempotent on a
> natural key. Reprocessing is safe; it can't double-count."

### 2.5 Why batch the writes?

One network/disk round-trip per record is wasteful. Batching amortises the
fixed cost of a write across many records. This is literally what Kinesis
Firehose does before it writes to S3, and what `drain_stream` does with
`BATCH_SIZE`.

### 2.6 Infrastructure as Code — the book's headline

Clicking services together in a web console is not repeatable, not reviewable,
and not safe. Instead:
- **Declare** infrastructure in code (`infra/main.tf`).
- **Version** it in git — every change is a reviewable pull request.
- **Dry-run** it with `terraform plan` before `terraform apply` (this is "test
  before you apply").
- **Modularise** it — one module per component — so you can reuse it across dev,
  staging, and prod by changing a variable, not the code.

> **Say this:** "I never click infra together by hand. It's Terraform in git, so
> changes are diffable PRs and `plan` shows me the blast radius before I apply."

### 2.7 CI/CD — automate the boring, error-prone parts

`.github/workflows/ci.yml` runs the tests **and** a full end-to-end smoke run on
every push and PR. Nothing merges red. This is the book's "use a CI/CD pipeline"
rule: the machine, not a human's memory, guarantees quality on every change.

### 2.8 Testing philosophy the book preaches

- **Small committed dataset** (`data/sample_events.jsonl`) — big enough to be
  representative, small enough to eyeball.
- **Text formats** (JSONL) — they diff cleanly in version control.
- **Fast, isolated tests** — each test in `tests/` uses a fresh temp file/DB, so
  they don't depend on each other or on order.
- **Test the seams** — `test_ingest.py` spins up the real HTTP server and talks
  to it over a socket: an end-to-end test, not just units.

---

## Part 3 — Mock interview questions (with the answers in this repo)

1. **"Walk me through a data pipeline you'd build to ingest clickstream events."**
   → `README.md`'s diagram: ingest→stream→persist→query, and *why* each stage.

2. **"Your consumer receives the same event twice. What happens?"**
   → Nothing bad: idempotent write keyed on `event_id` (`persist.py`). Explain
   at-least-once delivery.

3. **"Traffic spikes 10x for five minutes. Does anything fall over?"**
   → No: the stream buffers; the consumer drains at its own rate (decoupling).
   Name *consumer lag* as the metric you'd watch.

4. **"How do you deploy this so a teammate can reproduce it?"**
   → IaC in `infra/`, in git, applied via `plan`/`apply`; config via variables,
   not code edits.

5. **"How do you know a change didn't break the pipeline?"**
   → CI runs the suite + an end-to-end smoke run on every PR
   (`.github/workflows/ci.yml`).

6. **"Why SQLite / why not a 'real' database?"**
   → It's the simplest thing that demonstrates persistence + SQL analytics with
   zero setup. Then explain the scale-up path: Firehose→S3(Parquet)→Athena, or
   Redshift/Snowflake/BigQuery. Show you know *why* you'd move, not just that
   you would.

7. **"The customer changes the event schema next week. Now what?"**
   → Additive, optional fields; version the schema; old and new events coexist.
   Validation lives in one place (`validate.py`) so the change is localised.

8. **"What would you monitor in production?"**
   → Per-stage counts (this repo already prints accepted/rejected/written/
   skipped), plus latency, consumer lag, and error rate — with alerts.

---

## Part 4 — How to *practise* with this repo

1. `python run_pipeline.py batch` — narrate each printed line out loud.
2. Break something on purpose (add a bad event to the sample file) and predict
   the output before running.
3. Run `python run_pipeline.py serve` and POST both a good and a bad event with
   `curl`; explain each response code.
4. Read one `pipeline/*.py` file and its matching `tests/*` file together; the
   test is the spec.
5. Open `infra/main.tf` and, for each resource, say the local file it maps to.

If you can do all five without notes, you can hold your own in the interview.

---

### A note on the FDE mindset

The technical content above matters, but the role is ultimately about
**reducing a messy real-world problem to a simple system you can explain.** This
whole repo is an exercise in exactly that: a six-service AWS architecture
reduced to five short, readable files that still demonstrate every core idea.
That reduction — and being able to teach it back — *is* the job.

# Mock Interview — the harder scenarios

The [FDE Interview Guide](FDE_INTERVIEW_GUIDE.md) covers the fundamentals. This
document is the next level: **open-ended scenario questions** of the kind a
senior interviewer uses to find the edge of what you know. There's rarely one
right answer — they're watching *how you reason*, whether you name trade-offs,
and whether you can stay concrete.

**How to answer any of these well (a repeatable structure):**

1. **Clarify** the constraint — "What's the volume? How fresh does it need to be?
   Can we tolerate duplicates?" Asking is a signal, not a weakness.
2. **State the failure mode** you're protecting against, out loud.
3. **Give the simplest design that works**, then the scale-up path.
4. **Name what you'd monitor** to know it's healthy.

Each scenario below lists **what they're testing** and **a strong answer**,
grounded in this repo where possible.

---

## 1. The schema changes mid-flight

> *"The customer adds a `currency` field to purchase events next week, and
> renames `value` to `amount`. Events already in the pipeline use the old shape.
> Walk me through handling this without downtime or data loss."*

**Testing:** schema evolution — the single most common real-world pipeline pain.

**Strong answer:**
- **Additive first.** Adding `currency` is easy: make it *optional* in
  validation (`validate.py` already treats `value` as optional). Old events
  without it stay valid; new events include it.
- **Renames are two deploys, never one.** Never rename in place. Instead:
  (1) accept *both* `value` and `amount`, writing to one canonical column;
  (2) migrate producers to send `amount`; (3) once no `value` events arrive
  for a full retention window, drop the alias. This is the *expand → migrate →
  contract* pattern.
- **Version the schema.** Stamp events with `schema_version`. Your consumer
  branches on it. Old and new coexist; you're never forced into a big-bang
  cutover.
- **Because validation lives in one file**, the change is localised — that's a
  deliberate design property, not luck.

**Follow-up they'll ask:** *"What about the millions of old rows in the
warehouse?"* → That's a **backfill** (next question).

---

## 2. The backfill

> *"You shipped a bug: for two weeks, `purchase.value` was stored as cents, not
> dollars. There are 40M affected rows. Fix it."*

**Testing:** do you understand that raw data is sacred and derived data is
disposable?

**Strong answer:**
- **Never mutate in place blindly.** First quantify the blast radius with a
  query (`WHERE event_type='purchase' AND timestamp BETWEEN ...`).
- **Prefer replay over patch.** This is *why we keep an append-only stream/raw
  store.* If the raw events are intact, the fix is: correct the transform, then
  **reprocess from the offset** where the bug started. Reads are non-destructive
  and offset-based (`Stream.read(from_offset=...)`), so replay is a first-class
  operation, not a heroic migration.
- **If you must patch stored rows**, do it **idempotently and in batches**, write
  to a *new* column/table, validate, then swap. Keep the original until you've
  verified.
- **Guard against double-application.** A backfill that runs twice must not halve
  the values again — same idempotency discipline as the write path.

**The one-liner:** *"Keep raw data immutable and transforms replayable, and most
'backfills' become 'reprocess from offset N'."*

---

## 3. The consumer falls behind

> *"Your persist stage is processing 1,000 events/sec but ingestion is now taking
> 5,000/sec. What happens, how do you detect it, and how do you fix it?"*

**Testing:** backpressure and the metric that matters — **consumer lag**.

**Strong answer:**
- **What happens:** nothing *breaks* immediately — that's the point of the log.
  Events accumulate; the consumer's offset falls further behind the newest
  offset. The gap is **consumer lag**. The danger is silent: latency grows and,
  if lag exceeds your retention window, you start *losing* unread data.
- **Detect:** alert on `newest_offset - consumer_offset` (and its rate of
  change). Rising lag is your earliest warning, well before users notice.
- **Fix, in order of preference:**
  1. **Parallelize** — more shards/partitions + more consumer instances. (Our
     local log is one shard; Kinesis/Kafka scale by partition count.)
  2. **Make the consumer cheaper** — bigger batches, fewer round-trips
     (`BATCH_SIZE`), bulk inserts.
  3. **Shed or tier load** — sample low-value events, or push overflow to a
     slower path.
- **Watch for hot partitions:** if you shard by `user_id` and one user is 90% of
  traffic, adding shards won't help. Choose a **high-cardinality, evenly-
  distributed partition key.**

---

## 4. The duplicate storm

> *"A producer's retry logic goes haywire and sends every event 50 times. Your
> dashboards — do the numbers change?"*

**Testing:** whether idempotency is real in your design or just a word.

**Strong answer:**
- **No, the numbers hold.** Persistence is idempotent on `event_id`
  (`INSERT OR IGNORE`), so the 49 replays are no-ops. See
  `tests/test_persist.py::test_persist_is_idempotent_on_event_id`.
- **This is why at-least-once + idempotent-write is the standard pattern** —
  it's cheaper and more robust than trying to guarantee exactly-once delivery.
- **Caveat worth raising unprompted:** idempotency requires a *stable, unique*
  key. If the producer generates a *new* `event_id` per retry, dedup fails —
  now you'd need a content hash or a dedup window. Naming this shows senior
  judgment.

---

## 5. The poison message

> *"One event has a body that crashes your consumer every time it's processed.
> The consumer restarts, hits it again, crashes again — forever. Now what?"*

**Testing:** fault isolation; do you know about dead-letter queues?

**Strong answer:**
- **The failure mode:** a single bad record blocks the *entire* stream behind it
  — a head-of-line block. One poison message stalls everything.
- **The fix:** after N failed attempts, **route the record to a dead-letter
  queue (DLQ)** and advance the offset. The pipeline keeps flowing; the bad
  record is quarantined for a human to inspect.
- **Prevention:** strong edge validation (`validate.py`) catches most poison
  before it enters the stream. But defend in depth — `drain_stream` *also*
  skips invalid records rather than crashing, because you never fully trust an
  upstream stage.
- **Monitor DLQ depth** — a rising DLQ is a real incident, not noise.

---

## 6. Ordering and late-arriving data

> *"Events can arrive out of order — a mobile client was offline and flushes an
> hour-old event now. Your 'events per minute' chart. Is it correct?"*

**Testing:** event-time vs processing-time — a concept that separates juniors
from seniors.

**Strong answer:**
- **Distinguish the two clocks:** *processing time* (when you received it) vs
  *event time* (the `timestamp` field, when it actually happened). Aggregations
  should almost always use **event time**.
- **Late data breaks naive windows.** If you finalized the 10:00 bucket at 10:01
  and a 10:00 event arrives at 11:00, it's lost from that bucket.
- **The tools:** **watermarks** (a heuristic for "we've probably seen everything
  up to time T") and **allowed lateness** (keep windows open a bit longer, or
  emit corrections). Trade freshness against completeness — you can't max both.
- **Ordering:** streams only guarantee order *within a partition*. If you need
  per-user ordering, partition by `user_id`. Global total order is expensive and
  usually unnecessary — challenge the requirement.

---

## 7. Exactly-once — the trap question

> *"The customer insists on exactly-once processing. Deliver it."*

**Testing:** do you know that true end-to-end exactly-once is largely a myth,
and what people actually mean by it?

**Strong answer:**
- **Push back gently:** true exactly-once *delivery* across a network is
  effectively impossible (the two-generals problem). What's achievable is
  **exactly-once *effect*** = at-least-once delivery **+** idempotent processing.
- **That's exactly what this pipeline does:** duplicates may arrive, but the
  idempotent write means the *effect* is once. For most "exactly-once"
  requirements, that satisfies the real need.
- **When they need stronger:** transactional sinks (write + offset-commit in one
  atomic transaction) get you closer, at a real throughput/complexity cost.
  Name the cost — don't pretend it's free.

---

## 8. The FDE-flavored curveballs

These test the *forward-deployed* part specifically: messy reality, constrained
environments, and non-technical audiences.

> *"The customer's environment has no internet access and no managed cloud
> services. Deploy this pipeline there."*

- **This is why the local version has zero dependencies.** It runs on a bare
  Python install. In an air-gapped environment you lean on self-hostable
  equivalents (a single-node Kafka or even a file/DB-backed queue), and you
  vendor your dependencies. The *architecture* is identical; only the
  *implementations* of each stage swap out. Being able to say "the stages are an
  interface, the AWS services are one implementation" is the whole point.

> *"The customer's historical data is a pile of inconsistent CSVs — missing
> fields, mixed date formats, duplicates. Get it into the pipeline."*

- **Meet the data where it is.** Write an adapter that maps their mess onto your
  clean event schema, and route anything unmappable to a reject file for review
  (same spirit as edge validation). Never let dirty data silently define your
  schema. Quantify the reject rate and show it to the customer — that number is
  often the most valuable thing you deliver in week one.

> *"Explain this pipeline to the customer's VP of Marketing, who is not
> technical."*

- **Drop the jargon, keep one analogy.** *"Events come in the front door where we
  check their ID and turn away anyone suspicious (validation). The good ones wait
  in an orderly line (the stream) so a rush at the door never overwhelms us. We
  file them in batches (persistence), and then you can ask any question of the
  files with a simple query (analytics)."* The ability to teach it back at this
  level is, unironically, the core FDE skill — see the closing note in the
  interview guide.

---

## 9. Observability — "how would you know it's broken at 3am?"

**Testing:** production maturity.

**Strong answer — the minimum viable set:**
- **Per-stage counts** (this pipeline already prints accepted / rejected /
  written / skipped) — a sudden jump in `rejected` means an upstream change.
- **Consumer lag** — the earliest indicator of trouble (scenario 3).
- **Latency** — p50/p95/p99 end-to-end, not just averages (averages hide the
  pain).
- **Error rate + DLQ depth** — poison messages and systemic failures.
- **Alert on rate-of-change, not just thresholds** — "rejects doubled in 5
  minutes" catches problems a static threshold misses.
- **The principle:** you should learn about an incident from a *metric*, not from
  the customer.

---

## Self-drill checklist

Can you answer each of these in under two minutes, out loud, naming a trade-off?

- [ ] Rename a field with zero downtime (expand → migrate → contract)
- [ ] Fix 40M bad rows (replay from offset vs in-place patch)
- [ ] Consumer is behind — detect and fix (lag, partitions, batching, hot keys)
- [ ] 50x duplicates — why the numbers hold (idempotent write on a stable key)
- [ ] A record crashes the consumer forever (DLQ + head-of-line blocking)
- [ ] Out-of-order / late events (event time vs processing time, watermarks)
- [ ] "Give me exactly-once" (at-least-once + idempotent = exactly-once effect)
- [ ] Deploy with no cloud (stages are an interface; swap implementations)
- [ ] Messy customer CSVs (adapter + reject file + report the reject rate)
- [ ] Explain it to a non-technical VP (the front-door analogy)
- [ ] Know it's broken at 3am (per-stage counts, lag, latency, DLQ, rate-alerts)

If you can check every box, you're interviewing above the bar for the role.

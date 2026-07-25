# Case study — real-time fraud surveillance for Singapore's Shared Responsibility Framework (SRF)

> **Status: design / proposal.** This document is the write-up we agreed to do
> *before* building. It presents a current Singapore banking regulation, the
> problem it creates, and a concrete design for demonstrating a solution as a
> **parallel, self-contained module** (`examples/srf_fraud/`) that imports the
> existing pipeline stages without changing them. No code has been written yet;
> this is the plan to review first.

---

## 1. The regulation (the "why now")

Singapore has moved bank-side scam liability from voluntary goodwill to a
**legal duty with uncapped financial exposure**. Three instruments stack up:

- **Shared Responsibility Framework (SRF)** — effective **16 Dec 2024**. Defines
  a "waterfall" of who pays when a customer loses money to a **phishing scam**:
  the **financial institution (FI) bears the loss first if it breached its
  duties**, then the telco, and only then the consumer. If the FI breached a
  duty, payouts are **full, with no liability cap**.
- **Real-time fraud surveillance duty** — the SRF's anti-scam duty for FIs, in
  force from **16 Jun 2025** (after a 6-month transition). FIs must run
  **round-the-clock monitoring** to **detect and mitigate accounts having
  material sums rapidly wiped out** by unauthorised transactions.
- **Protection from Scams Act 2025** — effective **1 Jul 2025**. Provides legal
  backing for FIs (and the police) to **restrict/hold** a customer's banking
  transactions when there's reason to believe they're being scammed.

**Scope to be precise about (interviewers love precision):** the SRF covers
**digital phishing scams** specifically. It does *not* cover malware-enabled
scams or authorised-push-payment scams where the victim knowingly transfers.
Getting this boundary right matters — over-claiming coverage is a red flag.

*Sources:*
[MAS – Combatting Scams](https://www.mas.gov.sg/regulation/combatting-scams) ·
[MAS – Guidelines on the Shared Responsibility Framework](https://www.mas.gov.sg/regulation/guidelines/guidelines-on-shared-responsibility-framework) ·
[MAS – Written reply to PQs on SRF and fraud surveillance (2026)](https://www.mas.gov.sg/news/parliamentary-replies/2026/written-reply-to-pqs-on-srf-and-fraud-surveillance) ·
[A&O Shearman – Singapore's Shared Responsibility Framework](https://www.aoshearman.com/en/insights/ao-shearman-on-fintech-and-digital-assets/combatting-payment-account-fraud-singapores-shared-responsibility-framework)

---

## 2. The problem, stated as an engineer

Strip away the legal language and the bank's obligation is a **streaming
detection problem** with a **hard latency budget**:

> For every outbound transfer, decide *within seconds* whether it fits a
> "rapid account drain" pattern, and if so **raise an alert and optionally hold
> the transfer** — then keep an **auditable record** proving the surveillance ran.

That is almost exactly the shape of the pipeline in this repo. Transactions are
just another kind of event; "real-time surveillance" is a consumer that scores
events off the stream as they arrive. The only genuinely new piece is a
**detection stage** and an **alert sink**.

---

## 3. Why this maps cleanly onto the existing pipeline

The core pipeline is `ingest → stream → persist → query`. This case study adds
**one stage** and **one sink**, reusing everything else unchanged:

```
                                    ┌──────────────────────────┐
 transfer  ──▶ ingest ──▶ stream ──▶│  DETECT (rule engine)    │──▶ persist ──▶ query
 events        (validate) (log,      │  velocity / new-payee /  │    (txns +      (audit
               at edge)   offsets,   │  amount-spike / odd-hour │    alerts)      reports)
                          replay)    └───────────┬──────────────┘
                                                 │ on hit
                                                 ▼
                                          ALERT / HOLD sink
                                          (SRF real-time duty)
```

The two properties the SRF cares about are properties the pipeline *already*
has, which is what makes this a strong demo:

- **Real-time** → the stream is a low-latency log; the detector reads new
  offsets as they land, so detection latency is "time to process one record."
- **Auditable** → every alert is persisted with the rule that fired and a
  timestamp, so the bank can *prove* surveillance ran on a given transaction —
  exactly what a regulator asks for after an incident.

---

## 4. Proposed module layout (`examples/srf_fraud/`)

Kept separate so the generic teaching pipeline stays pristine; this module
**imports** the core stages rather than modifying them.

```
examples/srf_fraud/
├── README.md              # the SRF story + how to run the demo
├── transactions.py        # transfer event schema + validation (reuses pipeline.validate style)
├── rules.py               # the detection rules, one small pure function each
├── detect.py              # the streaming detector: reads pipeline.Stream, applies rules, emits alerts
├── alerts.py              # the alert/hold sink + an `alerts` table (audit trail)
├── run_demo.py            # scripted "account drain" scenario, end to end
├── data/
│   └── scenario_drain.jsonl   # a small, hand-crafted phishing-drain sequence
└── tests/
    └── test_rules.py      # each rule tested against a labelled mini-dataset
```

**Design intent for each file:**

- **`transactions.py`** — a transfer event: `txn_id, account_id, payee_id,
  amount, currency, timestamp, channel`. Same "validate at the edge" discipline
  as `pipeline/validate.py`.
- **`rules.py`** — each rule is a **small, pure, individually testable function**
  returning `(fired: bool, reason: str)`. This is deliberate: rules are the part
  a compliance team will argue about, so they must be readable and unit-testable
  in isolation. Proposed starting set:
  | Rule | Fires when | SRF duty it serves |
  |---|---|---|
  | `rapid_drain` | ≥ N transfers **or** > $X cumulative from one account in a rolling T-minute window | "material sums rapidly wiped out" |
  | `new_payee_high_value` | first-ever payee **and** amount over a threshold | classic phishing mule pattern |
  | `amount_spike` | amount ≫ the account's recent typical transfer | anomaly detection |
  | `odd_hour` | transfer in a low-activity window (e.g. 2–5am local) | weak signal, combined with others |
- **`detect.py`** — reads the stream by offset, keeps the small rolling state the
  velocity rule needs, and on a hit writes an alert. Uses **event time** (the
  `timestamp` field), not processing time — see `docs/MOCK_INTERVIEW.md §6`.
- **`alerts.py`** — persists alerts idempotently (keyed on `txn_id + rule`), so
  reprocessing/replay can't double-alert. The `alerts` table *is* the audit
  trail.
- **`run_demo.py`** — plays `scenario_drain.jsonl` through the whole chain and
  prints: transfers seen, alerts raised, and which rule caught the drain.

---

## 5. The scripted scenario (what the demo will show)

A believable phishing-drain sequence in `scenario_drain.jsonl`: a normal account
history, then — after a "phish" — a burst of rapid transfers to a brand-new
payee in the small hours. Running the demo should print something like:

```
transactions processed: 12
ALERT txn=t8  rule=rapid_drain        (4 transfers / $9,400 in 3 min)
ALERT txn=t8  rule=new_payee_high_value ($4,000 to never-seen payee)
HELD  txn=t9  (account under active drain alert)
audit: 12 transactions scored, 3 alerts persisted with timestamps + reasons
```

The narrative for a non-technical stakeholder: *"Money started leaving the
account faster than this customer ever moves it, to someone they'd never paid,
at 3am. We caught it on the 4th transfer, alerted, and held the 5th — and we can
prove to MAS exactly what we saw and when."*

---

## 6. The trade-offs to name out loud (the senior signal)

- **False positives vs false negatives.** Tighten the rules and you block
  legitimate large transfers (angry customers); loosen them and drains slip
  through (uncapped liability). The demo should make this dial explicit rather
  than pretend a perfect threshold exists.
- **Latency budget.** Holding a transfer means deciding *before* settlement.
  That's why detection lives on the stream, not in a nightly batch job.
- **Rules vs ML.** We start with transparent rules because a compliance team
  must be able to read and defend them. ML scoring is a natural follow-on, but
  explainability is a regulatory requirement, not a nice-to-have — name that.
- **Scope honesty.** This addresses the *phishing-drain* pattern the SRF targets.
  It is not a general AML/CFT system (that's MAS Notice 626 — a different,
  larger problem).
- **State & scale.** The velocity rule needs per-account rolling state. Locally
  that's an in-memory dict; at a real bank it's a keyed state store (e.g. Redis
  or a stream processor's managed state), partitioned by `account_id`.

---

## 7. How this strengthens the FDE story

It upgrades the portfolio piece from "a generic data pipeline" to **"a real-time
transaction-monitoring pipeline aligned to a live Singapore regulation with
uncapped bank liability."** It demonstrates the three things the interview tests
at once: an **end-to-end system**, **named trade-offs**, and the ability to
**explain a regulated problem to a non-technical audience** — while reusing the
exact same architecture, which itself proves the "stages are an interface"
point from `docs/ARCHITECTURE.md`.

---

## 8. Proposed next step

If this design looks right, the build order would be:

1. `transactions.py` + `data/scenario_drain.jsonl` (define the shape + scenario)
2. `rules.py` + `tests/test_rules.py` (the part worth testing hardest, TDD)
3. `detect.py` + `alerts.py` (wire rules onto the stream, add the audit sink)
4. `run_demo.py` + `examples/srf_fraud/README.md` (the runnable narrative)
5. CI: extend the existing workflow to run the new tests too

Say the word and I'll build it in that order on the same PR.

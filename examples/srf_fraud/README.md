# `examples/srf_fraud/` — real-time fraud surveillance for Singapore's SRF

A self-contained case study that applies the generic pipeline in this repo to a
**current, high-stakes regulation**: Singapore's **Shared Responsibility
Framework (SRF)**, which requires banks to run **round-the-clock real-time
surveillance** for accounts being rapidly drained by phishing scams — with
**uncapped liability** if they fail. Full write-up and sources:
[`docs/SRF_CASE_STUDY.md`](../../docs/SRF_CASE_STUDY.md).

This module **imports the core `pipeline` stages unchanged** — proving the
"stages are an interface" point: same architecture, new domain.

## Run it

```bash
python -m examples.srf_fraud.run_demo
```

Expected output (a scripted phishing drain of `acc-victim`, plus a normal
`acc-normal` that correctly triggers nothing):

```
transactions processed: 10  (skipped 0)
------------------------------------------------------------
ALERT txn=  t6  rule=new_payee_high_value  (1800.00 to never-seen payee mule-88)
ALERT txn=  t6  rule=amount_spike          (1800.00 vs typical 20.10)
ALERT txn=  t6  rule=odd_hour              (transfer at 03:01)
ALERT txn=  t7  rule=amount_spike          (2600.00 vs typical 316.75)
ALERT txn=  t7  rule=odd_hour              (transfer at 03:03)
ALERT txn=  t8  rule=rapid_drain           (3 transfers in 10 min)
ALERT txn=  t8  rule=odd_hour              (transfer at 03:05)
HELD  txn=  t7  (account under active drain alert)
HELD  txn=  t8  (account under active drain alert)
------------------------------------------------------------
audit: 7 alerts and 2 holds persisted with timestamps + reasons
```

## How it maps to the pipeline + the regulation

| File | Role | Reuses / SRF duty |
| --- | --- | --- |
| `transactions.py` | transfer schema + edge validation | mirrors `pipeline/validate.py` |
| `rules.py` | 4 pure, testable detection rules | the surveillance logic |
| `detect.py` | streaming detector over the log | reuses `pipeline.stream.Stream` |
| `alerts.py` | alert + hold sink (the **audit trail**) | idempotent, like `pipeline/persist.py` |
| `run_demo.py` | scripted end-to-end drain scenario | the story for a stakeholder |

## The rules (what "surveillance" concretely means)

| Rule | Fires when | SRF concern |
| --- | --- | --- |
| `rapid_drain` | ≥3 transfers **or** >$5,000 from one account in 10 min | "material sums rapidly wiped out" |
| `new_payee_high_value` | first-ever payee **and** amount ≥ $1,000 | classic mule pattern |
| `amount_spike` | amount > 5× the account's recent typical | anomaly |
| `odd_hour` | transfer between 02:00–05:00 | weak signal, combined with others |

Thresholds are demo defaults, centralised as rule keyword args so a compliance
team can tune them without touching logic. The trade-offs (false positives vs
uncapped liability, latency, rules-vs-ML, scope) are discussed in the case study.

> **Scope honesty:** this addresses the *phishing-drain* pattern the SRF targets.
> It is not a general AML/CFT system (that's MAS Notice 626 — a larger problem).

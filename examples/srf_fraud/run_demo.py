"""Runnable end-to-end SRF fraud-surveillance demo.

    python -m examples.srf_fraud.run_demo

Plays a scripted phishing-drain scenario through the real `pipeline` Stream and
the detector, then prints what surveillance caught -- the story you'd tell a
non-technical stakeholder.
"""
import json
from pathlib import Path

from examples.srf_fraud import alerts as alert_sink
from examples.srf_fraud import detect
from pipeline.stream import Stream

SCENARIO = Path(__file__).resolve().parent / "data" / "scenario_drain.jsonl"


def main():
    # Load the scenario into a throwaway stream sitting next to the data file.
    stream = Stream(SCENARIO.parent / "_demo_stream.jsonl")
    stream.clear()
    with SCENARIO.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                stream.put(json.loads(line))

    conn = alert_sink.connect()  # in-memory audit store for the demo
    summary = detect.run(stream, conn)

    print(f"transactions processed: {summary['processed']}  (skipped {summary['skipped']})")
    print("-" * 60)
    for a in summary["alerts"]:
        print(f"ALERT txn={a['txn_id']:>4}  rule={a['rule']:<21} ({a['reason']})")
    for h in summary["holds"]:
        print(f"HELD  txn={h['txn_id']:>4}  ({h['reason']})")
    print("-" * 60)
    print(
        f"audit: {alert_sink.alert_count(conn)} alerts and "
        f"{alert_sink.hold_count(conn)} holds persisted with timestamps + reasons"
    )
    stream.clear()


if __name__ == "__main__":
    main()

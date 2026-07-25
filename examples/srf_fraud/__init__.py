"""SRF fraud-surveillance demo -- a parallel case study built on the core pipeline.

This package applies the generic `pipeline/` stages to a concrete, current
regulatory problem: Singapore's Shared Responsibility Framework (SRF), which
requires banks to run real-time surveillance for accounts being rapidly drained
by phishing scams. See docs/SRF_CASE_STUDY.md for the full write-up.

It imports the core stages (notably `pipeline.stream.Stream`) unchanged, proving
the "stages are an interface" point: the same architecture, a new domain.
"""

"""A minimal, runnable data pipeline that mirrors a classic AWS architecture.

The stages, and their real-world AWS equivalents, are:

    ingest   -> API Gateway + a validation Lambda   (pipeline/ingest.py)
    stream   -> Kinesis Data Streams                 (pipeline/stream.py)
    persist  -> Kinesis Firehose writing to S3       (pipeline/persist.py)
    query    -> Amazon Athena                        (pipeline/query.py)

Everything here uses only the Python standard library, so the whole pipeline
runs with zero third-party dependencies. That is a deliberate teaching choice:
the fewer moving parts a system has, the easier it is to reason about, test,
and deploy at a customer site -- which is the daily job of a forward deployed
engineer.
"""

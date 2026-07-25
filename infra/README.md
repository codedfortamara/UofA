# `infra/` — Infrastructure as Code (IaC)

This directory holds the **Terraform** description of the AWS version of the
pipeline. It exists to teach the book's central lesson: **your infrastructure
should be code, not clicks.**

## Why not just click it together in the AWS console?

The book (chapter *"Automate Your Infrastructure"*) gives the answer directly:

- **Repeatability.** A pipeline is ~6 components (API Gateway, Lambda, Kinesis
  Stream, Firehose, S3, Athena) each needing config, IAM roles, and ACLs. Wiring
  that by hand once is slow; doing it "again, and again, and again" for every
  environment is where mistakes — and security breaches — happen.
- **Reviewability.** Code lives in version control, so a change to your
  infrastructure is a **pull request** you can diff, review, and roll back.
- **Testability.** `terraform plan` is a **dry run**: it shows exactly what will
  change *before* anything does. That is the book's "test the code before
  applying it" rule, built into the tool.

## The mental model

```
terraform plan    ->  "here is what I WOULD change"   (safe, read-only)
terraform apply   ->  actually make the change
terraform destroy ->  tear it all down
```

Terraform keeps a **state file** mapping your code to the real resources it
created, so it always knows the difference between what you declared and what
exists. That diff is the whole magic of IaC.

## How this maps to the local pipeline

| `infra/main.tf` resource            | Local file            | Concept          |
| ----------------------------------- | --------------------- | ---------------- |
| `aws_lambda_function.validate`      | `pipeline/validate.py`| edge validation  |
| `aws_kinesis_stream.ingest`         | `pipeline/stream.py`  | streaming buffer |
| `aws_kinesis_firehose_delivery_...` | `pipeline/persist.py` | batched writes   |
| `aws_s3_bucket.events`              | SQLite warehouse file | persistence      |
| `aws_iam_role.*`                    | *(none — local trust)*| least privilege  |

> **Note:** `main.tf` is intentionally *not* runnable as-is (it would create
> billable AWS resources and needs the Lambda zip + full IAM policies). It is a
> teaching artifact. The *behaviour* it describes is what actually runs, for
> free, in the `pipeline/` package.

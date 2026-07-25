# -----------------------------------------------------------------------------
# infra/main.tf  --  Infrastructure as Code (Terraform), for TEACHING.
#
# This file describes the *real AWS version* of the pipeline that pipeline/
# implements locally. It is heavily commented and is NOT meant to be `terraform
# apply`-ed as-is (it would create billable resources and needs IAM wiring).
# Its job is to show what "automate your infrastructure" concretely looks like.
#
# The book's rules, made real:
#   * "Never use the web console"  -> every resource below is code, not clicks.
#   * "Make it modular"            -> each `resource` block is one component.
#   * "Use a version-control system" -> this file lives in git; changes are PRs.
#   * "Test the code before applying" -> `terraform plan` is the dry run.
# -----------------------------------------------------------------------------

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# A "variable" is an input -- the seam between code and environment, exactly like
# pipeline/config.py. You pass it per environment (dev/staging/prod) so the same
# code deploys everywhere without edits.
variable "environment" {
  description = "Deployment environment name, e.g. dev or prod."
  type        = string
  default     = "dev"
}

provider "aws" {
  region = "us-east-1"
}

# --- Persistence: S3 bucket (local equivalent: the SQLite warehouse file) ------
resource "aws_s3_bucket" "events" {
  bucket = "mini-pipeline-events-${var.environment}"
}

# --- Streaming: Kinesis Data Stream (local equivalent: pipeline/stream.py) ------
resource "aws_kinesis_stream" "ingest" {
  name        = "mini-pipeline-ingest-${var.environment}"
  shard_count = 1 # one shard == our single append-only log
}

# --- Delivery: Firehose stream Kinesis -> S3 (local equivalent: persist.py) -----
# Firehose is the batching writer: it buffers records and flushes them to S3.
resource "aws_kinesis_firehose_delivery_stream" "to_s3" {
  name        = "mini-pipeline-firehose-${var.environment}"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose.arn
    bucket_arn = aws_s3_bucket.events.arn
    # Buffer up to 5 MB or 300 seconds, whichever comes first -- the real-world
    # version of BATCH_SIZE in pipeline/config.py.
    buffering_size     = 5
    buffering_interval = 300
  }
}

# --- Ingestion: the validation Lambda (local equivalent: validate.py) ----------
resource "aws_lambda_function" "validate" {
  function_name = "mini-pipeline-validate-${var.environment}"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.11"
  handler       = "handler.lambda_handler"
  filename      = "build/validate.zip" # produced by your CI build step
}

# --- IAM: least-privilege roles ("handle permissions and access management") ---
# The book calls out that a real pipeline is ~6 components and most of the pain
# is IAM. These roles are why: each component gets ONLY the permissions it needs.
resource "aws_iam_role" "firehose" {
  name = "mini-pipeline-firehose-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "firehose.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = "mini-pipeline-lambda-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# `terraform output` surfaces values other tools/humans need after an apply.
output "bucket_name" {
  value = aws_s3_bucket.events.bucket
}

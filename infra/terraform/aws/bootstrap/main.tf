# The bucket every other root module of an AWS account keeps its state in, and the table a plan
# locks it by, made once with local state: both outlive the state that made them
# (terraform.tfstate here is gitignored and may be lost).

provider "aws" {
  region = var.region
}

variable "region" {
  type        = string
  description = "The region the state is kept in."
  default     = "us-east-1"
}

data "aws_caller_identity" "this" {}

resource "aws_s3_bucket" "state" {
  bucket        = "pinecall-terraform-state-${data.aws_caller_identity.this.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Old versions of the state kept 90 days: enough to roll back a bad apply.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
  depends_on = [aws_s3_bucket_versioning.state]
}

# One plan at a time on a state: Terraform 1.5 locks an S3 state by a row of this table.
resource "aws_dynamodb_table" "locks" {
  name         = "pinecall-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.locks.name
}

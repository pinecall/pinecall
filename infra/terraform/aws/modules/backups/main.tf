# Where a cluster's Postgres keeps its past: a bucket its WAL and its base backups go to, through
# the Barman Cloud plugin, as a role of its own that touches this bucket alone (modules/identity:
# the Postgres pods' Kubernetes service account acts as it). The plugin's retention policy
# (charts/postgres) deletes what is older than the window, so no rule here expires a current object:
# one of its own could delete a WAL file a kept base backup still needs.

data "aws_caller_identity" "this" {}

resource "aws_s3_bucket" "postgres" {
  bucket        = "pinecall-${var.name}-postgres-${data.aws_caller_identity.this.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "postgres" {
  bucket                  = aws_s3_bucket.postgres.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# The backups' role can delete what it wrote: a deleted object is kept seven days as an old version,
# and the role cannot change the bucket to shorten that.
resource "aws_s3_bucket_versioning" "postgres" {
  bucket = aws_s3_bucket.postgres.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "postgres" {
  bucket = aws_s3_bucket.postgres.id
  rule {
    id     = "deleted-a-week-ago"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
  depends_on = [aws_s3_bucket_versioning.postgres]
}

data "aws_iam_policy_document" "postgres" {
  # The plugin lists the bucket before it writes.
  statement {
    sid       = "ListTheBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.postgres.arn]
  }
  statement {
    sid       = "ReadAndWriteItsObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.postgres.arn}/*"]
  }
}

module "postgres" {
  source           = "../identity"
  name             = "pinecall-${var.name}-postgres"
  description      = "Pinecall's Postgres backups, ${var.name}"
  issuer           = var.issuer
  service_accounts = var.postgres_service_accounts
  policy           = data.aws_iam_policy_document.postgres.json
}

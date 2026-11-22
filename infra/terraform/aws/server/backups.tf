# Where the server's Postgres keeps its past: its WAL and its nightly base backups, sent by the
# server itself (`PINECALL_BACKUP_URL`, runtime/docs/the-runtime-cli.md) as the machine's own role.
# The backups' own retention deletes what is older than its window, so no rule here expires a
# current object: one of its own could delete a WAL file a kept base backup still needs.
resource "aws_s3_bucket" "postgres" {
  bucket        = "pinecall-${var.name}-server-postgres-${data.aws_caller_identity.this.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "postgres" {
  bucket                  = aws_s3_bucket.postgres.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# The server can delete what it wrote: a deleted object is kept seven days as an old version, and
# the server's role cannot change the bucket to shorten that.
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

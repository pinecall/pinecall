output "bucket" {
  value = aws_s3_bucket.postgres.bucket
}

# The annotations that make the Postgres pods' ServiceAccount the role that writes the bucket.
output "identity" {
  value = module.postgres.annotations
}

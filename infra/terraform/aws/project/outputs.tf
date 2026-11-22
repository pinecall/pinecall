# What `make image` and the operator are told of what the account holds.

output "registry" {
  description = "Where the images live, as an image's name begins."
  value       = "${data.aws_caller_identity.this.account_id}.dkr.ecr.${var.region}.amazonaws.com/pinecall"
}

output "build_project" {
  description = "The CodeBuild project that builds the images (`make image`)."
  value       = aws_codebuild_project.image.name
}

output "build_source" {
  description = "The bucket a build's context is uploaded to."
  value       = aws_s3_bucket.source.bucket
}

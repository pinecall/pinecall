# Terraform and the provider this root is planned with, and where its state is kept.

terraform {
  required_version = "~> 1.5.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # bucket, key, region and dynamodb_table: the operator's project.backend.hcl (`make tf-init ROOT=project`).
  backend "s3" {}
}

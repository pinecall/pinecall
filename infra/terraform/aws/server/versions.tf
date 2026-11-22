# One server and, beside it, the hosted apps' machine: Terraform and the provider it is planned
# with, and where its state is kept.
terraform {
  required_version = "~> 1.5.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # bucket, key, region and dynamodb_table: the operator's <name>.backend.hcl (`make tf-init`), one
  # state per deployment.
  backend "s3" {}
}

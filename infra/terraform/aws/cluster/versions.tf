# One cluster: Terraform and the providers it is planned with, and where its state is kept.

terraform {
  required_version = "~> 1.5.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
  }
  # bucket, key, region and dynamodb_table: the operator's <name>.backend.hcl (`make tf-init`), one
  # state per cluster.
  backend "s3" {}
}

# Terraform and the provider this root is planned with, and where its state is kept.

terraform {
  required_version = "~> 1.5.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # bucket and prefix: the operator's project.backend.hcl (`terraform init -backend-config=…`).
  backend "gcs" {}
}

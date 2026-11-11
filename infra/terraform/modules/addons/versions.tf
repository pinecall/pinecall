# The providers this module's resources are of; the root that calls it fixes their versions.

terraform {
  required_version = ">= 1.5"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = ">= 3.0"
    }
  }
}

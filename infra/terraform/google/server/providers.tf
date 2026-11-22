# Who Terraform acts as, per provider: the operator's own logins, never a stored key.
provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

# Route 53 holds the names' zone (dns_zone); its credentials are the operator's AWS login.
provider "aws" {
  region = "us-east-1"
}

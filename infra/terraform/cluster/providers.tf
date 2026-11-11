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

# Helm reaches the cluster as the gcloud login, by a token Terraform reads, never a stored file.
data "google_client_config" "me" {}

provider "helm" {
  kubernetes = {
    host                   = "https://${module.gke.endpoint}"
    token                  = data.google_client_config.me.access_token
    cluster_ca_certificate = base64decode(module.gke.ca_certificate)
  }
}

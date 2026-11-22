# Who Terraform acts as: the operator's gcloud login, in the project given.

provider "google" {
  project = var.project
  region  = var.region
}

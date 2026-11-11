# What the project holds for every cluster in it: the registry the images live in and the identity
# Cloud Build builds them as (`make image`). Each cluster (cluster/, once per ENV) is made beside
# these.

provider "google" {
  project = var.project
  region  = var.region
}

variable "project" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

module "registry" {
  source = "../modules/registry"
  region = var.region
}

module "build" {
  source  = "../modules/build"
  project = var.project
}

output "registry" {
  value = module.registry.url
}

output "build_service_account" {
  value = module.build.service_account
}

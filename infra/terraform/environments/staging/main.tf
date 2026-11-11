# Staging: the whole cluster on Google Cloud, where each phase is proven with calls before
# production. Made for the proof and destroyed after it (a second cluster's fee is paid while it
# stands; the free tier covers one zonal cluster).

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
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
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # bucket and prefix: the operator's <env>.backend.hcl (`make tf-init`).
  backend "gcs" {}
}

provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

variable "project" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-c"
}

# Route 53 holds the names' zone (dns_zone); its credentials are the operator's AWS login.
provider "aws" {
  region = "us-east-1"
}

module "edge" {
  source    = "../../modules/edge"
  name      = "staging"
  zone      = var.dns_zone
  names     = var.names
  sip_names = var.sip_names
  region    = var.region
  pages     = var.pages
  # The fence's networks (ops/terraform/staging.fence.tfvars.json, `make tf-fence`), and the
  # lab's generator while it stands.
  sip_sources = concat(var.sip_sources, [for lab in module.lab : "${lab.public_address}/32"])
}

variable "pages" {
  type        = string
  description = "The domain the apps' own pages are served under (`<app>--<org>.<pages>`); empty serves none."
  default     = ""
}

variable "dns_zone" {
  type        = string
  description = "The Route 53 zone every name below is a record of."
}

variable "names" {
  type        = list(string)
  description = "The names the cluster is served at, every one of them both worlds; the first is PINECALL_DOMAIN."
}

variable "sip_names" {
  type        = map(string)
  description = "Each world's SIP name, at the world's media address: a carrier's alone (PINECALL_SIP_DOMAIN, PINECALL_SANDBOX_SIP_DOMAIN)."
}

# The networks the orgs' carriers call from, as the gateway approved them: written by `make tf-fence`
# into ops/terraform/<env>.fence.tfvars.json, a file that is versioned there and read before a plan.
# No default, on purpose: with one, a checkout that lacked the file planned the firewall's removal and
# 5060 closed to every carrier (2026-10-21). A plan with no file fails; an env with no carrier says `[]`.
variable "sip_sources" {
  type        = list(string)
  description = "The networks 5060 opens to, each a CIDR; an empty list opens it to nobody."

  validation {
    condition     = alltrue([for source in var.sip_sources : can(cidrnetmask(source)) || can(cidrhost(source, 0))])
    error_message = "Each of sip_sources is a network in CIDR form (203.0.113.0/24, 2001:db8::/32)."
  }
}

# The voice lab beside the cluster, for a proof with calls (infra/lab): `-var lab=true`.
variable "lab" {
  type    = bool
  default = false
}

module "lab" {
  count      = var.lab ? 1 : 0
  source     = "../../modules/lab"
  zone       = var.zone
  pods_range = var.ranges.pods
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

# After the cluster and its pools: a chart waits for its pods, which need a node to run on.
module "addons" {
  source                  = "../../modules/addons"
  secrets_service_account = module.secrets.sync_service_account
  depends_on              = [module.gke]
}

module "backups" {
  source  = "../../modules/backups"
  project = var.project
  name    = "staging"
  region  = var.region
}

module "kubeip" {
  source  = "../../modules/kubeip"
  project = var.project
  name    = "staging"
}

module "secrets" {
  source  = "../../modules/secrets"
  project = var.project
  name    = "staging"
  # The lab's object store takes any key; the operator puts one by hand as production's is put.
  given      = ["s3-access-key-id", "s3-secret-access-key"]
  depends_on = [module.gke]
}

# The cluster's private ranges (modules/gke); the charts are told the first two.
variable "ranges" {
  type = object({ nodes = string, pods = string, services = string })
}

module "gke" {
  source              = "../../modules/gke"
  project             = var.project
  name                = "staging"
  region              = var.region
  zone                = var.zone
  nodes_range         = var.ranges.nodes
  pods_range          = var.ranges.pods
  services_range      = var.ranges.services
  deletion_protection = false
}

output "cluster" {
  value = module.gke.cluster
}

output "location" {
  value = module.gke.location
}

output "secrets_sync_service_account" {
  value = module.secrets.sync_service_account
}

output "ingress_address_name" {
  value = module.edge.ingress_address_name
}

output "ingress_address" {
  value = module.edge.ingress_address
}

output "lab_generator" {
  value = [for lab in module.lab : { name = lab.name, internal = lab.internal_address, public = lab.public_address }]
}

output "postgres_backups_bucket" {
  value = module.backups.bucket
}

output "postgres_backups_service_account" {
  value = module.backups.service_account
}

output "media_addresses" {
  value = module.edge.media_addresses
}

output "kubeip_service_account" {
  value = module.kubeip.service_account
}

output "certificate_map" {
  value = module.edge.certificate_map
}

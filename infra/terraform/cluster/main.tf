# One cluster of Pinecall: both worlds at one name. Which cluster it is, is its variables: `make`
# gives `name` (CLUSTER), and every name, address, range and account of the operator who runs it comes
# from their own <name>.tfvars, with the state in their own bucket (<name>.backend.hcl), both outside
# this tree (OPS). Production and a staging made for a proof are the same code.

locals {
  # An org's two envs, each with its own media node, workers and runner.
  envs = ["production", "sandbox"]
  # Each world's runner key, minted by the gateway (`keys runner`) and put by the operator.
  runner_keys = var.hosting ? [for env in local.envs : "runner-key-${env}"] : []
}

module "gke" {
  source              = "../modules/gke"
  project             = var.project
  name                = var.name
  region              = var.region
  zone                = var.zone
  nodes_range         = var.ranges.nodes
  pods_range          = var.ranges.pods
  services_range      = var.ranges.services
  deletion_protection = var.deletion_protection
}

module "edge" {
  source         = "../modules/edge"
  name           = var.name
  zone           = var.dns_zone
  names          = var.names
  point_names    = var.point_names
  sip_names      = var.sip_names
  kept_addresses = var.kept_addresses
  services       = var.services
  point_services = var.point_services
  region         = var.region
  pages          = var.pages
  # The fence's networks (ops/terraform/<name>.fence.tfvars.json, `make tf-fence`), and the lab's
  # generator while it stands.
  media_tag   = module.gke.media_tag
  sip_sources = concat(var.sip_sources, [for lab in module.lab : "${lab.public_address}/32"])
}

module "secrets" {
  source        = "../modules/secrets"
  project       = var.project
  name          = var.name
  workload_pool = module.gke.workload_pool
  given         = concat(var.given_secrets, local.runner_keys)
}

# After the cluster and its pools: a chart waits for its pods, which need a node to run on.
module "addons" {
  source                  = "../modules/addons"
  secrets_service_account = module.secrets.sync_service_account
  depends_on              = [module.gke]
}

module "backups" {
  source        = "../modules/backups"
  workload_pool = module.gke.workload_pool
  project       = var.project
  name          = var.name
  region        = var.region
}

module "kubeip" {
  source        = "../modules/kubeip"
  workload_pool = module.gke.workload_pool
  project       = var.project
  name          = var.name
}

module "alerts" {
  count  = length(var.alert_emails) > 0 ? 1 : 0
  source = "../modules/alerts"
  name   = var.name
  domain = var.names[0]
  emails = var.alert_emails
}

# Production's alerts were made before a cluster could have none (2026-11-12).
moved {
  from = module.alerts
  to   = module.alerts[0]
}

module "notify" {
  count            = var.firebase_project == null ? 0 : 1
  source           = "../modules/notify"
  project          = var.project
  name             = var.name
  firebase_project = var.firebase_project
  workload_pool    = module.gke.workload_pool
}

module "hosting" {
  count          = var.hosting ? 1 : 0
  source         = "../modules/hosting"
  project        = var.project
  name           = var.name
  region         = var.region
  nodes_range    = var.hosting_ranges.nodes
  pods_range     = var.hosting_ranges.pods
  services_range = var.hosting_ranges.services
  runner_keys    = { for env in local.envs : env => module.secrets.ids["runner-key-${env}"] }
}

module "lab" {
  count      = var.lab ? 1 : 0
  source     = "../modules/lab"
  zone       = var.zone
  pods_range = var.ranges.pods
}

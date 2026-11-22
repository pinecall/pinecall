# One cluster of Pinecall on AWS: both envs at one name. Which cluster it is, is its variables:
# `make` gives `name`, and every name, address, range and account of the operator who runs it comes
# from their own <cluster>.tfvars, with the state in their own bucket (<cluster>.backend.hcl), both
# outside this tree (OPS). Production and a staging made for a proof are the same code. It ends as
# terraform/google/cluster does, in `chart_values`: what was made, in the words the charts read.

locals {
  # An org's two envs, each with its own media node, workers and runner.
  envs = ["production", "sandbox"]
  # Each env's runner key, minted by the gateway (`keys runner`) and put by the operator.
  runner_keys = var.hosting ? [for env in local.envs : "runner-key-${env}"] : []
}

module "network" {
  source = "../modules/network"
  name   = var.name
  range  = var.ranges.vpc
  zones  = var.zones
}

module "edge" {
  source         = "../modules/edge"
  name           = var.name
  vpc            = module.network.vpc
  zone           = var.dns_zone
  names          = var.names
  point_names    = var.point_names
  sip_names      = var.sip_names
  point_sip      = var.point_sip
  services       = var.services
  point_services = var.point_services
  pages          = var.pages
  sip_sources    = var.sip_sources
}

module "eks" {
  source                = "../modules/eks"
  name                  = var.name
  kubernetes            = var.kubernetes
  subnets               = module.network.subnets
  nodes_subnet          = module.network.nodes_subnet
  services_range        = var.ranges.services
  api_sources           = var.api_sources
  admins                = var.admins
  core_type             = var.pools.core
  media_type            = var.pools.media
  workers_type          = var.pools.workers
  workers_max           = var.pools.workers_max
  media_security_groups = module.edge.media_security_groups
  deletion_protection   = var.deletion_protection
}

module "secrets" {
  source        = "../modules/secrets"
  name          = var.name
  issuer        = module.eks.issuer
  given         = concat(var.given_secrets, local.runner_keys)
  recovery_days = var.secrets_recovery_days
}

module "backups" {
  source = "../modules/backups"
  name   = var.name
  issuer = module.eks.issuer
}

module "kubeip" {
  source = "../modules/kubeip"
  name   = var.name
  issuer = module.eks.issuer
}

# After the cluster and its pools: a chart waits for its pods, which need a node to run on.
module "controllers" {
  source     = "../modules/controllers"
  name       = var.name
  cluster    = module.eks.cluster
  vpc        = module.network.vpc
  issuer     = module.eks.issuer
  depends_on = [module.eks]
}

module "addons" {
  source           = "../../modules/addons"
  secrets_identity = module.secrets.sync_identity
  depends_on       = [module.eks]
}

module "hosting" {
  count                  = var.hosting ? 1 : 0
  source                 = "../modules/hosting"
  name                   = var.name
  cluster                = module.eks.cluster
  vpc                    = module.network.vpc
  zone                   = module.network.zone
  range                  = module.network.hosting_range
  route_table            = module.network.route_table
  cluster_security_group = module.eks.cluster_security_group
  type                   = var.pools.hosting
  most                   = var.pools.hosting_max
}

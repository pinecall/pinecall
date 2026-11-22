# What the cluster's charts and the operator are told about what was made.

output "cluster" {
  description = "The cluster's name, as aws and kubectl know it (`aws eks update-kubeconfig --name <it>`)."
  value       = module.eks.cluster
}

output "region" {
  description = "The region the cluster runs in."
  value       = var.region
}

output "media_addresses" {
  description = "Each env's media address: its LiveKit's and its SIP's."
  value       = module.edge.media_addresses
}

output "load_balancer" {
  description = "The name of the load balancer charts/edge's Gateway is served by, once released."
  value       = module.edge.load_balancer
}

output "postgres_backups_bucket" {
  description = "The bucket Postgres's backups and its log are kept in."
  value       = module.backups.bucket
}

output "secrets" {
  description = "Each secret's name in Secrets Manager: where a `given` one is put."
  value       = module.secrets.ids
}

output "hosting" {
  description = "The hosted apps' pool, as charts/hosting is told of it (infra/values/hosting-example.yaml); none while hosting is off."
  value = var.hosting ? {
    pool           = module.hosting[0].pool
    runtimeHandler = module.hosting[0].runtime_handler
    secretPrefix   = module.secrets.secret_prefix
    services       = var.ranges.services
  } : null
}

# What Terraform made, in the words the charts read (infra/charts, values.yaml): `make values`
# writes it beside the operator's own values, which then hold decisions alone. The same keys as
# terraform/google/cluster's, each said this cloud's way.
output "chart_values" {
  description = "The charts' values that are facts of this cluster: its names, its addresses, its ranges, its identities."
  value = {
    cluster = var.name
    domain  = var.names[0]
    pages   = var.pages
    # Each env's SIP name and the media address it is reached at (modules/edge makes an address
    # for every SIP name).
    envs = {
      for env, address in module.edge.media_addresses :
      env => { sipDomain = var.sip_names[env], mediaAddress = address }
    }
    # None named: the cluster's default class, the disks' driver's own on gp3 (modules/eks).
    storageClass = ""
    secrets = {
      prefix = module.secrets.secret_prefix
      provider = {
        aws = {
          service = "SecretsManager"
          region  = var.region
          # The store's own identity: a token of External Secrets' ServiceAccount, exchanged with
          # AWS directly, never the node's metadata service, which answers the node alone.
          auth = { jwt = { serviceAccountRef = module.secrets.reader } }
        }
      }
    }
    # An Application Load Balancer made by the load balancer controller for the chart's Gateway
    # (modules/controllers), with Certificate Manager's certificates (modules/edge).
    ingress = {
      className   = "pinecall-alb"
      annotations = {}
      addresses   = []
      aws = {
        loadBalancer = module.edge.load_balancer
        certificates = module.edge.certificates
        subnets      = module.network.balancer_subnets
      }
    }
    postgres = {
      backups = {
        destination               = "s3://${module.backups.bucket}/postgres"
        credentials               = { s3Credentials = { inheritFromIAMRole = true } }
        serviceAccountAnnotations = module.backups.identity
      }
    }
    # Nobody collects yet: the alerts of charts/pinecall wait for a Prometheus on the cluster
    # (`prometheus-operator`), which no module here installs.
    monitoring = { collector = "none", namespace = "" }
    kubeip = {
      annotations = module.kubeip.identity
      # An Elastic IP is found by its tag (modules/edge), in AWS's own filter words.
      filter = "Name=tag:pinecall-media,Values=%s"
      region = module.kubeip.region
    }
    media = { nodeNetwork = module.network.nodes_range }
    gateway = {
      podNetwork = module.network.nodes_range
      # The load balancer's own subnets: it ends every X-Forwarded-For with the caller's address,
      # and no request reaches a gateway from the internet but through it.
      trustedProxies = join(",", module.network.balancer_ranges)
    }
  }
}

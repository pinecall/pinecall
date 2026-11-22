# What the cluster's charts and the operator are told about what was made.

output "cluster" {
  description = "The cluster's name, as gcloud and kubectl know it."
  value       = module.gke.cluster
}

output "location" {
  description = "The zone the cluster runs in."
  value       = module.gke.location
}

output "secrets_sync_service_account" {
  description = "The identity External Secrets reads Secret Manager as."
  value       = module.secrets.sync_service_account
}

output "ingress_address_name" {
  description = "The reserved name of the Gateway's address."
  value       = module.edge.ingress_address_name
}

output "ingress_address" {
  description = "The address every name of the cluster points at."
  value       = module.edge.ingress_address
}

output "media_addresses" {
  description = "Each world's media address: its LiveKit's and its SIP's."
  value       = module.edge.media_addresses
}

output "certificate_map" {
  description = "The certificate map the Gateway serves its names with."
  value       = module.edge.certificate_map
}

output "postgres_backups_bucket" {
  description = "The bucket Postgres's backups and its log are kept in."
  value       = module.backups.bucket
}

output "postgres_backups_service_account" {
  description = "The identity Postgres writes its backups as."
  value       = module.backups.service_account
}

output "kubeip_service_account" {
  description = "The identity kubeip gives a media node its address as."
  value       = module.kubeip.service_account
}

output "notify_service_account" {
  description = "The identity the operator's notifier signs pushes as; none without a Firebase project."
  value       = one(module.notify[*].service_account)
}

output "hosting" {
  description = "The hosting cluster and its runners' identities; none while hosting is off."
  value       = var.hosting ? module.hosting[0] : null
}

output "lab_generator" {
  description = "The lab's call generator while it stands: its name and its two addresses."
  value       = [for lab in module.lab : { name = lab.name, internal = lab.internal_address, public = lab.public_address }]
}

# What Terraform made, in the words the charts read (infra/charts, values.yaml): `make values`
# writes it beside the operator's own values, which then hold decisions alone. Until 2026-11-12
# each of these was typed again by hand into that file, and one had drifted.
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
    storageClass = "standard-rwo"
    secrets = {
      prefix = module.secrets.secret_prefix
      provider = {
        gcpsm = {
          projectID = var.project
          # The store's own identity: a token of External Secrets' ServiceAccount, exchanged with
          # Google directly, never the node's metadata server (which a new node offers seconds
          # after the pod).
          auth = {
            workloadIdentity = {
              clusterProjectID  = var.project
              clusterLocation   = module.gke.location
              clusterName       = module.gke.cluster
              serviceAccountRef = module.secrets.reader
            }
          }
        }
      }
    }
    # Google's HTTPS load balancer, the global address and Certificate Manager's map (modules/edge).
    ingress = {
      className   = "gke-l7-global-external-managed"
      annotations = { "networking.gke.io/certmap" = module.edge.certificate_map }
      addresses   = [{ type = "NamedAddress", value = module.edge.ingress_address_name }]
      gkePolicies = true
    }
    postgres = {
      backups = {
        destination               = "gs://${module.backups.bucket}/postgres"
        credentials               = { googleCredentials = { gkeEnvironment = true } }
        serviceAccountAnnotations = { "iam.gke.io/gcp-service-account" = module.backups.service_account }
      }
    }
    # Google's Managed Prometheus collects; modules/alerts makes the alerts in Cloud Monitoring.
    monitoring = { collector = "gmp", namespace = "gmp-system" }
    kubeip     = { identity = module.kubeip.service_account }
    media      = { nodeNetwork = var.ranges.nodes }
    gateway = {
      podNetwork = var.ranges.pods
      # Google's load balancer ends every X-Forwarded-For with its own address: believed beside
      # Google's two ranges, the caller's is the one before it.
      trustedProxies = "35.191.0.0/16,130.211.0.0/22,${module.edge.ingress_address}/32"
    }
  }
}

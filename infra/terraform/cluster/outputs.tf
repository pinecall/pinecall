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

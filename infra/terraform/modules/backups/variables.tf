variable "project" {
  type = string
}

variable "name" {
  type        = string
  description = "The world-pair: staging, production."
}

variable "region" {
  type = string
}

# The Postgres pods' Kubernetes service account, and a restore drill's: a Cluster recovered from
# the bucket beside the live one, read as the same identity (charts/postgres, README).
variable "postgres_service_accounts" {
  type        = list(string)
  description = "The Kubernetes service accounts that act as the backups' identity: namespace/name."
  default     = ["default/pinecall-postgres", "default/pinecall-postgres-restore"]
}

variable "workload_pool" {
  type        = string
  description = "The cluster's workload identity pool (modules/gke): where its ServiceAccounts are named."
}

variable "name" {
  type        = string
  description = "staging or production."
}

# The Postgres pods' Kubernetes service account, and a restore drill's: a Cluster recovered from
# the bucket beside the live one, read as the same identity (charts/postgres, README).
variable "postgres_service_accounts" {
  type        = list(string)
  description = "The Kubernetes service accounts that act as the backups' identity: namespace/name."
  default     = ["default/pinecall-postgres", "default/pinecall-postgres-restore"]
}

variable "issuer" {
  type        = object({ arn = string, host = string })
  description = "The cluster's token issuer (modules/eks): where its ServiceAccounts are named."
}

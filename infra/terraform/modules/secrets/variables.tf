variable "project" {
  type = string
}

variable "name" {
  type        = string
  description = "staging or production: the secrets are pinecall-<name>-*."
}

variable "given" {
  type        = list(string)
  description = "The secrets the operator puts by hand, made here empty: vault-key, s3-secret-access-key."
  default     = []
}

variable "workload_pool" {
  type        = string
  description = "The cluster's workload identity pool (modules/gke): where its ServiceAccounts are named."
}

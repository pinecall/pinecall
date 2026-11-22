variable "name" {
  type        = string
  description = "staging or production: the secrets are pinecall-<name>-*."
}

variable "given" {
  type        = list(string)
  description = "The secrets the operator puts by hand, made here empty: vault-key, s3-secret-access-key."
  default     = []
}

variable "issuer" {
  type        = object({ arn = string, host = string })
  description = "The cluster's token issuer (modules/eks): where its ServiceAccounts are named."
}

variable "recovery_days" {
  type        = number
  description = "How long a deleted secret is kept, and its name held: 7 to 30, or 0 for none."
  default     = 7
}

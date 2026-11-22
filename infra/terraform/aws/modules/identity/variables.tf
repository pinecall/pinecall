variable "name" {
  type        = string
  description = "The role's name."
}

variable "description" {
  type = string
}

variable "issuer" {
  type        = object({ arn = string, host = string })
  description = "The cluster's token issuer as IAM knows it (modules/eks, `issuer`)."
}

variable "service_accounts" {
  type        = list(string)
  description = "The Kubernetes ServiceAccounts that may act as the role, each `<namespace>/<name>`."
}

variable "policy" {
  type        = string
  description = "What the role may do, as a policy document; null where managed policies say it all."
  default     = null
}

variable "managed_policies" {
  type        = list(string)
  description = "AWS's own policies attached to the role, each by its ARN."
  default     = []
}

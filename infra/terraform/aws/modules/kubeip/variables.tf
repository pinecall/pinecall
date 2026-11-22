variable "name" {
  type        = string
  description = "staging or production."
}

variable "kubernetes_service_account" {
  type        = string
  description = "namespace/name of the service account kubeip's DaemonSet runs as."
  default     = "default/pinecall-kubeip"
}

variable "issuer" {
  type        = object({ arn = string, host = string })
  description = "The cluster's token issuer (modules/eks): where its ServiceAccounts are named."
}

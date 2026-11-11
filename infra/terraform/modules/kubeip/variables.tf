variable "project" {
  type = string
}

variable "name" {
  type        = string
  description = "The world-pair: staging, production."
}

variable "kubernetes_service_account" {
  type        = string
  description = "namespace/name of the service account kubeip's DaemonSet runs as."
  default     = "default/pinecall-kubeip"
}

variable "workload_pool" {
  type        = string
  description = "The cluster's workload identity pool (modules/gke): where its ServiceAccounts are named."
}

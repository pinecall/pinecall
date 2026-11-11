variable "project" {
  type = string
}

variable "name" {
  type        = string
  description = "The world-pair: staging, production."
}

variable "firebase_project" {
  type        = string
  description = "The Firebase project the app is registered in."
}

variable "kubernetes_service_account" {
  type        = string
  description = "namespace/name of the service account notify runs as."
  default     = "default/pinecall-notify"
}

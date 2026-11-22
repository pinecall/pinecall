variable "secrets_identity" {
  type        = map(string)
  description = "The annotations that make External Secrets' ServiceAccount the cloud identity that reads the secret store: on GKE `iam.gke.io/gcp-service-account = <email>`, on EKS `eks.amazonaws.com/role-arn = <arn>`."
}

variable "cnpg_chart" {
  type    = string
  default = "0.29.1"
}

variable "external_secrets_chart" {
  type    = string
  default = "2.11.0"
}

variable "cert_manager_chart" {
  type    = string
  default = "v1.21.2"
}

variable "barman_cloud_chart" {
  type    = string
  default = "0.8.1"
}

variable "keda_chart" {
  type    = string
  default = "2.21.0"
}

variable "secrets_service_account" {
  type        = string
  description = "The Google identity External Secrets Operator acts as (modules/secrets)."
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

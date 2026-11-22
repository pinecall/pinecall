variable "name" {
  type        = string
  description = "staging or production."
}

variable "cluster" {
  type        = string
  description = "The cluster's name (modules/eks)."
}

variable "vpc" {
  type = string
}

variable "issuer" {
  type        = object({ arn = string, host = string })
  description = "The cluster's token issuer (modules/eks): where its ServiceAccounts are named."
}

variable "worker_grace_seconds" {
  type        = number
  description = "How long a worker's pod is given to drain its calls before its node is taken."
  default     = 900
}

# The Gateway API's release and the hash of its standard-install.yaml: the one the load balancer
# controller's release below is built against.
variable "gateway_api" {
  type    = string
  default = "v1.6.0"
}

variable "gateway_api_sha256" {
  type    = string
  default = "a557172e8348f758479e9ee4000bbbb4b4aa48302a6b73461823ea5349bad56d"
}

# load-balancer-policy.json beside this file is this release's own: they move together.
variable "load_balancer_chart" {
  type    = string
  default = "3.6.3"
}

variable "autoscaler_chart" {
  type    = string
  default = "9.60.0"
}

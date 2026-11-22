variable "name" {
  type        = string
  description = "staging or production: the network is pinecall-<name>."
}

variable "range" {
  type        = string
  description = "The VPC's range, a /16: its subnets are cut from it."
}

variable "zones" {
  type        = list(string)
  description = "Two availability zones: every node runs in the first."

  validation {
    condition     = length(var.zones) == 2 && var.zones[0] != var.zones[1]
    error_message = "Two different zones: the nodes' and a second one for the control plane and the load balancer."
  }
}

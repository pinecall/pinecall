variable "name" {
  type = string
}

variable "vpc" {
  type        = string
  description = "The VPC the media nodes' security groups are made in (modules/network)."
}

variable "rtp_ports" {
  type    = string
  default = "10000-10199"
}

variable "sip_sources" {
  type        = list(string)
  description = "The networks 5060 opens to: the carriers' signalling edges. Empty opens it to nobody."
}

variable "zone" {
  type        = string
  description = "The Route 53 zone the names are records of."
}

variable "names" {
  type = list(string)
}

# Off while another stack points the names elsewhere, and before the front door's first release:
# the certificates are proved and issued all the same, and the names move when this turns on.
variable "point_names" {
  type    = bool
  default = true
}

variable "services" {
  type        = list(string)
  description = "The names of the operator's own services served at this front door, each by its own chart."
  default     = []
}

variable "point_services" {
  type    = bool
  default = true
}

variable "sip_names" {
  type        = map(string)
  description = "Each env's SIP name, a carrier's alone: the env's media address."
}

# Off while the carriers still send each env's calls to another stack's address.
variable "point_sip" {
  type    = bool
  default = true
}

variable "pages" {
  type        = string
  description = "The domain the apps' own pages are served under, one label each; empty serves none."
  default     = ""
}

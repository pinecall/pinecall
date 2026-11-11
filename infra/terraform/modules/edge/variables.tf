variable "name" {
  type = string
}

variable "network" {
  type    = string
  default = "default"
}

variable "media_tag" {
  type        = string
  description = "The network tag of the worlds' media pools (modules/gke)."
  default     = "pinecall-gke-media"
}

variable "rtp_ports" {
  type    = string
  default = "10000-10199"
}

variable "sip_sources" {
  type        = list(string)
  description = "The networks 5060 opens to: the carriers' signalling edges (and, in staging, the lab's generator). Empty opens it to nobody."
}

variable "zone" {
  type        = string
  description = "The Route 53 zone the names are records of."
}

variable "names" {
  type = list(string)
}

# Off while another stack points the names elsewhere (production's box, until the cutover): the
# certificate is proved and issued all the same, and the names move when this turns on.
variable "point_names" {
  type    = bool
  default = true
}

variable "services" {
  type        = list(string)
  description = "The names of Pinecall's own services served at this front door, each by its own chart."
  default     = []
}

# Off while the services still answer elsewhere (the box): their certificate is issued all the
# same, and the names move when this turns on.
variable "point_services" {
  type    = bool
  default = true
}

variable "sip_names" {
  type        = map(string)
  description = "Each world's SIP name, a carrier's alone: the world's media address."
}

variable "pages" {
  type        = string
  description = "The domain the apps' own pages are served under, one label each; empty serves none."
  default     = ""
}

# A world whose address carriers and the orgs' PBXs already know keeps it: the address reserved
# before, by its name, becomes that world's media address instead of a new one.
variable "kept_addresses" {
  type        = map(string)
  description = "A world's media address kept from before, by its reserved name; the rest are made."
  default     = {}
}

variable "region" {
  type    = string
  default = "us-central1"
}

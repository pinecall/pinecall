variable "name" {
  type        = string
  description = "staging or production."
}

variable "cluster" {
  type        = string
  description = "The cluster the pool is of (modules/eks)."
}

variable "vpc" {
  type = string
}

variable "zone" {
  type = string
}

variable "range" {
  type        = string
  description = "The pool's own subnet, cut from the VPC's range (modules/network, `hosting_range`)."
}

variable "route_table" {
  type        = string
  description = "The VPC's route to the internet (modules/network)."
}

variable "cluster_security_group" {
  type        = string
  description = "The platform's side: the control plane and its nodes (modules/eks)."
}

# An app asks for a quarter of a core and half a gibibyte unless its release says otherwise: a
# t3a.large holds a dozen beside the two runners.
variable "type" {
  type = string
}

variable "least" {
  type    = number
  default = 1
}

variable "most" {
  type = number
}

variable "disk_gb" {
  type    = number
  default = 50
}

# gVisor's release and the hash of its x86_64 archive (gvisor.tar.bz2.sha512, beside it).
variable "gvisor" {
  type    = string
  default = "20261116.0"
}

variable "gvisor_sha512" {
  type    = string
  default = "c87d792d5842efb70c38ee822124cfe0821a547715e7abcf3f2b14997cd02784edaa0b91e238ec5c27a25a1b9e00bf98113398eb62a0778d8d20d4e222f8b0e0"
}

variable "zone" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-standard-8"
}

variable "pods_range" {
  type        = string
  description = "The cluster's pods: the workers reach the fakes from these addresses."
}

variable "network" {
  type    = string
  default = "default"
}

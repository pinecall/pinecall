# What the project's root is told: the operator's project.tfvars.

variable "project" {
  type        = string
  description = "The Google Cloud project every cluster is made in."
}

variable "region" {
  type        = string
  description = "The region the images' registry is in."
  default     = "us-central1"
}

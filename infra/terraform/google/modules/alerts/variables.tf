variable "name" {
  type        = string
  description = "The world-pair: staging, production."
}

variable "domain" {
  type        = string
  description = "The name the cluster is served at (PINECALL_DOMAIN), checked from outside."
}

variable "emails" {
  type        = list(string)
  description = "Who is told."
}

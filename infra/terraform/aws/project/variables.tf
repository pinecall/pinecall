# What the account's root is told: the operator's project.tfvars.

variable "region" {
  type        = string
  description = "The region the images' registry and their builder are in."
  default     = "us-east-1"
}

# A repository an image: Pinecall's own, and any of the operator's own services built the same way
# (a notifier, billing).
variable "images" {
  type        = list(string)
  description = "The images the registry holds, each a repository pinecall/<image>."
  default     = ["runtime", "postgres", "suite", "app", "mcp"]
}

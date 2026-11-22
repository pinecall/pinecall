# Who Terraform acts as: the operator's AWS login (~/.aws), never a stored key. Route 53, which
# holds the names' zone, is the same account's.
provider "aws" {
  region = var.region
}

# Who Terraform acts as: the operator's AWS login (~/.aws), in the region given.

provider "aws" {
  region = var.region
}

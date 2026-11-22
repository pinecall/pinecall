# Who Terraform acts as: the operator's AWS login (~/.aws), never a stored key. Route 53, which
# holds the names' zone, is the same account's.

provider "aws" {
  region = var.region
}

# Helm reaches the cluster as that login, by a token Terraform asks for, never a stored file.
data "aws_eks_cluster_auth" "me" {
  name = module.eks.cluster
}

provider "helm" {
  kubernetes = {
    host                   = module.eks.endpoint
    token                  = data.aws_eks_cluster_auth.me.token
    cluster_ca_certificate = base64decode(module.eks.ca_certificate)
  }
}

# A world-pair's Kubernetes cluster on AWS: Elastic Kubernetes Service, its nodes public and in one
# zone (modules/network says why), every pod's AWS access a role of its own (modules/identity).
# The pools are the ones a cluster has on any cloud: one for what both envs share (core: the
# gateways, Postgres, Redis, the operators), and per env a media pool (its LiveKit, its SIP, its
# core workers, on an address of its own) and a workers pool from 0, which the cluster autoscaler
# (modules/controllers) alone grows and shrinks, honouring a worker's grace period to drain its
# calls: a sandbox call never shares a machine with a production call.

data "aws_iam_policy_document" "cluster_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "pinecall-${var.name}-cluster"
  description        = "Pinecall ${var.name}: the cluster's control plane"
  assume_role_policy = data.aws_iam_policy_document.cluster_trust.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# The key the cluster's Secrets are sealed under before they are stored: what External Secrets
# syncs in (the vault key, the database's password) is never kept under a key that is not this
# account's own. Rotated each year by AWS; a month's notice before a deletion takes effect.
resource "aws_kms_key" "secrets" {
  description             = "Pinecall ${var.name}: the cluster's Kubernetes Secrets"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/pinecall-${var.name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_eks_cluster" "this" {
  name     = "pinecall-${var.name}"
  version  = var.kubernetes
  role_arn = aws_iam_role.cluster.arn

  encryption_config {
    resources = ["secrets"]
    provider {
      key_arn = aws_kms_key.secrets.arn
    }
  }

  vpc_config {
    subnet_ids = var.subnets
    # The API answers the operators' machines, which `make` runs on, and the nodes inside the VPC.
    endpoint_public_access  = true
    endpoint_private_access = true
    public_access_cidrs     = var.api_sources
  }

  kubernetes_network_config {
    service_ipv4_cidr = var.services_range
  }

  # Who reaches the API is said in IAM alone (access entries), never in a ConfigMap of the cluster;
  # whoever makes the cluster is its first admin.
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  # A version past its standard support is upgraded by AWS rather than billed at six times the
  # control plane's price to stay on it.
  upgrade_policy {
    support_type = "STANDARD"
  }

  deletion_protection = var.deletion_protection

  depends_on = [aws_iam_role_policy_attachment.cluster]
}

# The operators besides the one who made the cluster, each an IAM user or role, as its admins.
resource "aws_eks_access_entry" "admins" {
  for_each      = toset(var.admins)
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value
}

resource "aws_eks_access_policy_association" "admins" {
  for_each      = aws_eks_access_entry.admins
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }
}

# The cluster's token issuer, known to IAM: what lets a role name a Kubernetes ServiceAccount as
# the only one that may take it (modules/identity).
resource "aws_iam_openid_connect_provider" "this" {
  url            = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
}

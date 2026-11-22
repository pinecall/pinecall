# The identity kubeip acts as (charts/pinecall): it gives an env's media node the Elastic IP
# modules/edge reserved for that env, and can do nothing else. It reads every address and instance
# to find its own, and may attach or detach only an address that carries this cluster's
# `pinecall-media` tag.

data "aws_caller_identity" "this" {}

data "aws_region" "this" {}

locals {
  ec2 = "arn:aws:ec2:${data.aws_region.this.region}:${data.aws_caller_identity.this.account_id}"
}

data "aws_iam_policy_document" "kubeip" {
  statement {
    sid       = "FindTheAddressAndTheNode"
    actions   = ["ec2:DescribeAddresses", "ec2:DescribeInstances"]
    resources = ["*"]
  }
  statement {
    sid       = "MoveThisClustersMediaAddresses"
    actions   = ["ec2:AssociateAddress", "ec2:DisassociateAddress"]
    resources = ["${local.ec2}:elastic-ip/*"]
    condition {
      test     = "StringLike"
      variable = "aws:ResourceTag/pinecall-media"
      values   = ["${var.name}-*"]
    }
  }
  # An address is attached to an instance through its network interface: both are named too.
  statement {
    sid       = "OntoANode"
    actions   = ["ec2:AssociateAddress", "ec2:DisassociateAddress"]
    resources = ["${local.ec2}:instance/*", "${local.ec2}:network-interface/*"]
  }
}

module "kubeip" {
  source           = "../identity"
  name             = "pinecall-${var.name}-kubeip"
  description      = "Pinecall ${var.name}: kubeip"
  issuer           = var.issuer
  service_accounts = [var.kubernetes_service_account]
}

resource "aws_iam_role_policy" "kubeip" {
  name   = "move-the-media-addresses"
  role   = module.kubeip.name
  policy = data.aws_iam_policy_document.kubeip.json
}

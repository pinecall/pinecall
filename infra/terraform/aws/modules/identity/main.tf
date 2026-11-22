# An identity a pod acts as in AWS: a role that only the Kubernetes ServiceAccounts named can take,
# by a token the cluster signs and AWS checks against the cluster's own issuer (IAM roles for
# service accounts). No key is stored anywhere: the pod's token is rotated by the kubelet. What
# Workload Identity is on Google Cloud.

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.issuer.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.issuer.host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.issuer.host}:sub"
      values   = [for account in var.service_accounts : "system:serviceaccount:${replace(account, "/", ":")}"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.name
  description        = var.description
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

resource "aws_iam_role_policy" "this" {
  count  = var.policy == null ? 0 : 1
  name   = "own"
  role   = aws_iam_role.this.id
  policy = var.policy
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each   = toset(var.managed_policies)
  role       = aws_iam_role.this.name
  policy_arn = each.value
}

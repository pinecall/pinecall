# What an EKS cluster needs running on it that a GKE cluster is given by Google: the Gateway API's
# own definitions, the controller that makes a load balancer for a Gateway (charts/edge), and the
# autoscaler that grows and shrinks the workers' pools. Each pinned, each acting as a role of its
# own. The operators every cloud's cluster runs are terraform/modules/addons'.

# The Gateway API's standard channel, at the release the load balancer controller is built against:
# the definitions of Gateway and HTTPRoute, which charts/edge and charts/mcp declare. Applied with
# kubectl from the machine that plans (as `make` uses it), the file checked against its hash first.
resource "terraform_data" "gateway_api" {
  triggers_replace = [var.gateway_api, var.gateway_api_sha256]

  provisioner "local-exec" {
    command = "${path.module}/gateway-api.sh"
    environment = {
      CLUSTER = var.cluster
      REGION  = data.aws_region.this.region
      RELEASE = var.gateway_api
      SHA256  = var.gateway_api_sha256
    }
  }
}

data "aws_region" "this" {}

# The controller's policy as its release publishes it, kept beside this file at the same version
# (load-balancer-policy.json): what it needs to make and keep load balancers, target groups and
# their security groups.
module "load_balancer_identity" {
  source           = "../identity"
  name             = "pinecall-${var.name}-load-balancer"
  description      = "Pinecall ${var.name}: the load balancer controller"
  issuer           = var.issuer
  service_accounts = ["kube-system/aws-load-balancer-controller"]
}

resource "aws_iam_role_policy" "load_balancer" {
  name   = "make-load-balancers"
  role   = module.load_balancer_identity.name
  policy = file("${path.module}/load-balancer-policy.json")
}

resource "helm_release" "load_balancer" {
  name       = "aws-load-balancer-controller"
  namespace  = "kube-system"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.load_balancer_chart
  wait       = true
  values = [yamlencode({
    clusterName = var.cluster
    region      = data.aws_region.this.region
    # Told, never asked of the node's metadata service, which answers the node alone.
    vpcId = var.vpc
    serviceAccount = {
      name        = "aws-load-balancer-controller"
      annotations = module.load_balancer_identity.annotations
    }
    controllerConfig = { featureGates = { ALBGatewayAPI = true } }
    # One Gateway and no Service of type LoadBalancer: the webhook that would make this controller
    # every such Service's is left out.
    enableServiceMutatorWebhook = false
  })]
  depends_on = [terraform_data.gateway_api, aws_iam_role_policy.load_balancer]
}

# The autoscaler resizes the workers' Auto Scaling groups and no other: it reads every group to
# find them by their cluster's tag, and may change only those that carry it.
data "aws_iam_policy_document" "autoscaler" {
  statement {
    sid = "ReadTheGroupsAndTheirShapes"
    actions = [
      "autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeLaunchConfigurations", "autoscaling:DescribeScalingActivities",
      "ec2:DescribeImages", "ec2:DescribeInstanceTypes", "ec2:DescribeLaunchTemplateVersions",
      "ec2:GetInstanceTypesFromInstanceRequirements", "eks:DescribeNodegroup",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "ResizeThisClustersGroups"
    actions   = ["autoscaling:SetDesiredCapacity", "autoscaling:TerminateInstanceInAutoScalingGroup"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/k8s.io/cluster-autoscaler/${var.cluster}"
      values   = ["owned"]
    }
  }
}

module "autoscaler_identity" {
  source           = "../identity"
  name             = "pinecall-${var.name}-autoscaler"
  description      = "Pinecall ${var.name}: the cluster autoscaler"
  issuer           = var.issuer
  service_accounts = ["kube-system/cluster-autoscaler"]
}

resource "aws_iam_role_policy" "autoscaler" {
  name   = "resize-the-workers-pools"
  role   = module.autoscaler_identity.name
  policy = data.aws_iam_policy_document.autoscaler.json
}

resource "helm_release" "autoscaler" {
  name       = "cluster-autoscaler"
  namespace  = "kube-system"
  repository = "https://kubernetes.github.io/autoscaler"
  chart      = "cluster-autoscaler"
  version    = var.autoscaler_chart
  wait       = true
  values = [yamlencode({
    fullnameOverride = "cluster-autoscaler"
    cloudProvider    = "aws"
    awsRegion        = data.aws_region.this.region
    autoDiscovery    = { clusterName = var.cluster }
    rbac = {
      serviceAccount = {
        name        = "cluster-autoscaler"
        annotations = module.autoscaler_identity.annotations
      }
    }
    extraArgs = {
      # A worker drains its calls for up to fifteen minutes (charts/pinecall, _worker.tpl): a node
      # is never taken from under one sooner.
      "max-graceful-termination-sec" = var.worker_grace_seconds
      # A node empty for ten minutes goes; one whose pods hold only scratch space may go too.
      "scale-down-unneeded-time"      = "10m"
      "skip-nodes-with-local-storage" = false
      "balance-similar-node-groups"   = false
    }
  })]
}

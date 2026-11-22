# What a node may do as itself: join the cluster, give its pods their addresses, pull the
# registry's images. Pods act as their own roles (modules/identity), never as the node.
data "aws_iam_policy_document" "nodes_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "nodes" {
  name               = "pinecall-${var.name}-nodes"
  description        = "Pinecall ${var.name}: the cluster's nodes"
  assume_role_policy = data.aws_iam_policy_document.nodes_trust.json
}

resource "aws_iam_role_policy_attachment" "nodes" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly",
  ])
  role       = aws_iam_role.nodes.name
  policy_arn = each.value
}

locals {
  issuer = {
    arn  = aws_iam_openid_connect_provider.this.arn
    host = replace(aws_iam_openid_connect_provider.this.url, "https://", "")
  }
  # What every pool's nodes carry besides their own: the security group EKS makes for the cluster,
  # in which the control plane and the nodes reach each other.
  cluster_security_group = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  pools = merge(
    # Where an env's media runs on the core node, the node answers that env's media ports too.
    { core = { type = var.core_type, least = var.core_nodes, most = var.core_nodes, own = false, security_groups = var.core_holds_media ? var.media_security_groups : [] } },
    # One node: LiveKit and SIP hold the node's ports and announce the env's one address. Its ports
    # are opened by the security groups modules/edge makes.
    { for env, type in var.media_type : "media-${env}" => { type = type, least = 1, most = 1, own = true, security_groups = var.media_security_groups } },
    # An env's calls past its core workers; each env's ceiling is its own.
    { for env, most in var.workers_max : "workers-${env}" => { type = var.workers_type, least = 0, most = most, own = true, security_groups = [] } },
  )
}

# A launch template a pool: its security groups, a disk on gp3, and the metadata service answering
# the node alone (a token, one hop), so no pod reads the node's role from it.
resource "aws_launch_template" "pool" {
  for_each               = local.pools
  name                   = "pinecall-${var.name}-${each.key}"
  vpc_security_group_ids = concat([local.cluster_security_group], each.value.security_groups)

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = var.disk_gb
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "pinecall-${var.name}-${each.key}" }
  }
}

# The label and the taint are the ones the charts select and tolerate on any cloud
# (pinecall.io/pool): a media or workers pool takes its env's pods and nothing else.
resource "aws_eks_node_group" "pool" {
  for_each        = local.pools
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = each.key
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = [var.nodes_subnet]
  ami_type        = "AL2023_x86_64_STANDARD"
  instance_types  = [each.value.type]
  capacity_type   = "ON_DEMAND"

  scaling_config {
    min_size     = each.value.least
    max_size     = each.value.most
    desired_size = each.value.least
  }

  launch_template {
    id      = aws_launch_template.pool[each.key].id
    version = aws_launch_template.pool[each.key].latest_version
  }

  labels = { "pinecall.io/pool" = each.key }

  dynamic "taint" {
    for_each = each.value.own ? [each.key] : []
    content {
      key    = "pinecall.io/pool"
      value  = taint.value
      effect = "NO_SCHEDULE"
    }
  }

  update_config {
    max_unavailable = 1
  }

  # How many nodes a workers pool runs now is the autoscaler's to say, never a plan's.
  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }

  depends_on = [aws_iam_role_policy_attachment.nodes, aws_eks_addon.network]
}

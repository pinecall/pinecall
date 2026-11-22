# Where the orgs' hosted apps run on AWS (`pinecall deploy`): a pool of the cluster itself, fenced,
# rather than a second cluster and a second control plane to pay for. What keeps an org's code from
# the platform is said three times, each without the others:
#
#   the sandbox   each app's pod runs under gVisor (`runtimeClassName: gvisor`), which this pool's
#                 nodes alone have, installed at boot from one release checked against its hash
#   the network   the pool's nodes are in a subnet and a security group of their own: nothing of
#                 the platform's admits them but the cluster's API and its names, so a pod that
#                 left its sandbox still reaches no gateway, no database and no call
#   the policy    charts/hosting's NetworkPolicy, enforced by the cluster's network (modules/eks):
#                 an app reaches the internet and its runner, nothing private
#
# Each env's runner runs on this pool too (charts/hosting), so the platform's own nodes open no
# port to it. Optional: a runtime without it serves everything but hosted apps.

resource "aws_subnet" "hosting" {
  vpc_id                  = var.vpc
  availability_zone       = var.zone
  cidr_block              = var.range
  map_public_ip_on_launch = true
  tags                    = { Name = "pinecall-${var.name}-hosting" }
}

resource "aws_route_table_association" "hosting" {
  subnet_id      = aws_subnet.hosting.id
  route_table_id = var.route_table
}

resource "aws_security_group" "hosting" {
  name        = "pinecall-${var.name}-hosting"
  description = "Pinecall ${var.name}: the hosted apps' nodes, apart from the platform's"
  vpc_id      = var.vpc
  tags        = { Name = "pinecall-${var.name}-hosting" }
}

# Out: anywhere. What an app's pod may reach of it is the chart's policy; the platform's nodes
# admit none of it but the two rules below.
resource "aws_vpc_security_group_egress_rule" "out" {
  security_group_id = aws_security_group.hosting.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# Among the pool's own nodes: an app's pod and its runner.
resource "aws_vpc_security_group_ingress_rule" "own" {
  security_group_id            = aws_security_group.hosting.id
  description                  = "the pool's own nodes and pods"
  ip_protocol                  = "-1"
  referenced_security_group_id = aws_security_group.hosting.id
}

# The control plane to the pool's kubelets and pods (logs, exec, the admission of its webhooks).
resource "aws_vpc_security_group_ingress_rule" "from_cluster" {
  security_group_id            = aws_security_group.hosting.id
  description                  = "the cluster's control plane"
  ip_protocol                  = "-1"
  referenced_security_group_id = var.cluster_security_group
}

# The pool to the platform's side, two ports and no more: the cluster's API, which a node's kubelet
# and a runner ask, and the cluster's names, which a runner resolves the platform's public name by.
locals {
  to_cluster = {
    api       = { protocol = "tcp", port = 443 }
    names-udp = { protocol = "udp", port = 53 }
    names-tcp = { protocol = "tcp", port = 53 }
  }
}

resource "aws_vpc_security_group_ingress_rule" "to_cluster" {
  for_each                     = local.to_cluster
  security_group_id            = var.cluster_security_group
  description                  = "the hosted apps' pool: ${each.key}"
  ip_protocol                  = each.value.protocol
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = aws_security_group.hosting.id
}

# The pool's nodes as themselves, a role apart from the platform's nodes'.
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
  name               = "pinecall-${var.name}-hosting"
  description        = "Pinecall ${var.name}: the hosted apps' nodes"
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

# gVisor on the node before the kubelet starts: the release's archive checked against its hash and
# unpacked, and containerd told of the runtime `runsc`, which charts/hosting's RuntimeClass `gvisor`
# names. EKS adds its own part to this, the cluster's, and merges the two.
locals {
  user_data = <<-EOT
    MIME-Version: 1.0
    Content-Type: multipart/mixed; boundary="PINECALL"

    --PINECALL
    Content-Type: text/x-shellscript; charset="us-ascii"

    #!/bin/bash
    set -euo pipefail
    command -v bzip2 >/dev/null || dnf install -y -q bzip2
    work=$(mktemp -d)
    curl -fsSL -o "$work/gvisor.tar.bz2" "https://storage.googleapis.com/gvisor/releases/release/${var.gvisor}/x86_64/gvisor.tar.bz2"
    echo "${var.gvisor_sha512}  $work/gvisor.tar.bz2" | sha512sum -c -
    tar -xjf "$work/gvisor.tar.bz2" -C /usr/local/bin
    chmod -R a+rx /usr/local/bin/runsc /usr/local/bin/containerd-shim-runsc-v1 /usr/local/bin/gvisor-bin
    rm -rf "$work"

    --PINECALL
    Content-Type: application/node.eks.aws

    apiVersion: node.eks.aws/v1alpha1
    kind: NodeConfig
    spec:
      containerd:
        config: |
          [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.runsc]
          runtime_type = 'io.containerd.runsc.v1'

    --PINECALL--
  EOT
}

resource "aws_launch_template" "hosting" {
  name                   = "pinecall-${var.name}-hosting"
  vpc_security_group_ids = [aws_security_group.hosting.id]
  user_data              = base64encode(local.user_data)

  # The metadata service answers the node alone: no pod reads the node's role from it.
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
    tags          = { Name = "pinecall-${var.name}-hosting" }
  }
}

resource "aws_eks_node_group" "hosting" {
  cluster_name    = var.cluster
  node_group_name = "hosting"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = [aws_subnet.hosting.id]
  ami_type        = "AL2023_x86_64_STANDARD"
  instance_types  = [var.type]
  capacity_type   = "ON_DEMAND"

  scaling_config {
    min_size     = var.least
    max_size     = var.most
    desired_size = var.least
  }

  launch_template {
    id      = aws_launch_template.hosting.id
    version = aws_launch_template.hosting.latest_version
  }

  labels = { "pinecall.io/pool" = "hosting" }

  taint {
    key    = "pinecall.io/pool"
    value  = "hosting"
    effect = "NO_SCHEDULE"
  }

  update_config {
    max_unavailable = 1
  }

  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }

  depends_on = [aws_iam_role_policy_attachment.nodes, aws_route_table_association.hosting]
}

# What EKS runs on the cluster as its own add-ons, each at the version EKS gives the cluster's:
# the pods' network, which also enforces NetworkPolicy (the fence of charts/hosting, the two stores'
# policies of charts/pinecall); the Services' proxy; the cluster's names; and the disks' driver,
# with a default class on gp3, so a chart that names no class gets one.

resource "aws_eks_addon" "network" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "vpc-cni"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  configuration_values        = jsonencode({ enableNetworkPolicy = "true" })
}

resource "aws_eks_addon" "proxy" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "kube-proxy"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

# After the core pool: its pods need a node to run on, and the add-on waits for them.
resource "aws_eks_addon" "names" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "coredns"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on                  = [aws_eks_node_group.pool]
}

module "disks_identity" {
  source           = "../identity"
  name             = "pinecall-${var.name}-disks"
  description      = "Pinecall ${var.name}: the disks' driver (EBS CSI)"
  issuer           = local.issuer
  service_accounts = ["kube-system/ebs-csi-controller-sa"]
}

resource "aws_iam_role_policy_attachment" "disks" {
  role       = module.disks_identity.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "disks" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "aws-ebs-csi-driver"
  service_account_role_arn    = module.disks_identity.arn
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  configuration_values        = jsonencode({ defaultStorageClass = { enabled = true } })
  depends_on                  = [aws_eks_node_group.pool, aws_iam_role_policy_attachment.disks]
}

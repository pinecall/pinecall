output "cluster" {
  value = aws_eks_cluster.this.name
}

# What Helm reaches the cluster at: known in a plan whenever the cluster is only updated in place,
# so a change to the cluster never makes the addons' releases look new.
output "endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "ca_certificate" {
  value = aws_eks_cluster.this.certificate_authority[0].data
}

# The cluster's token issuer as IAM knows it: whoever makes a pod's identity (modules/identity)
# waits for the cluster by needing this, not by being told to.
output "issuer" {
  value = local.issuer
}

output "cluster_security_group" {
  value = local.cluster_security_group
}

# The Auto Scaling groups behind the workers' pools, which the autoscaler alone may resize.
output "scaled_groups" {
  value = flatten([for name, pool in aws_eks_node_group.pool : pool.resources[0].autoscaling_groups[*].name if startswith(name, "workers-")])
}

# Reached only once the pools stand: what runs on the cluster (modules/controllers, the addons)
# waits for nodes by needing this.
output "ready" {
  value = { for name, pool in aws_eks_node_group.pool : name => pool.status }
}

# What charts/hosting is told of the pool: its label and taint, which the runners and the RuntimeClass
# `gvisor` select and tolerate, and the handler that RuntimeClass names.
output "pool" {
  value = "hosting"
}

output "runtime_handler" {
  value = "runsc"
}

output "range" {
  value = aws_subnet.hosting.cidr_block
}

# Reached only once the pool stands.
output "ready" {
  value = aws_eks_node_group.hosting.status
}

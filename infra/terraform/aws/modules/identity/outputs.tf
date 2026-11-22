output "arn" {
  value = aws_iam_role.this.arn
}

# The annotation that makes a Kubernetes ServiceAccount this identity, as a chart's values take it.
output "annotations" {
  value = { "eks.amazonaws.com/role-arn" = aws_iam_role.this.arn }
}

# The annotations that make kubeip's ServiceAccount this role.
output "identity" {
  value = module.kubeip.annotations
}

output "region" {
  value = data.aws_region.this.region
}

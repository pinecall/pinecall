# The annotations that make External Secrets' ServiceAccount the role that reads the store.
output "sync_identity" {
  value = module.sync.annotations
}

output "secret_prefix" {
  value = "pinecall-${var.name}-"
}

# Each secret's name in Secrets Manager, by its name here.
output "ids" {
  value = { for name, secret in aws_secretsmanager_secret.this : name => secret.name }
}

# The ServiceAccount in the cluster that reads the store as that role.
output "reader" {
  value = local.reader
}

output "sync_service_account" {
  value = google_service_account.sync.email
}

output "secret_prefix" {
  value = "pinecall-${var.name}-"
}

# Each secret's id in Secret Manager, by its name here.
output "ids" {
  value = { for name, secret in google_secret_manager_secret.this : name => secret.secret_id }
}

# The ServiceAccount in the cluster that reads the store as `sync_service_account`.
output "reader" {
  value = local.reader
}

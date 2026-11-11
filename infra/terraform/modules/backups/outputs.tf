output "bucket" {
  value = google_storage_bucket.postgres.name
}

output "service_account" {
  value = google_service_account.postgres.email
}

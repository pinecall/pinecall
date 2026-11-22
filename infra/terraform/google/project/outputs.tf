# What `make image` and the operator are told of what the project holds.

output "registry" {
  description = "Where the images live, as an image's name begins."
  value       = "${var.region}-docker.pkg.dev/${google_artifact_registry_repository.images.project}/${google_artifact_registry_repository.images.repository_id}"
}

output "build_service_account" {
  description = "The identity Cloud Build builds the images as (`gcloud builds submit --service-account`)."
  value       = google_service_account.build.id
}

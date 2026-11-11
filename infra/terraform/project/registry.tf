# The images a cluster runs: Pinecall's own (the runtime, its Postgres), built by Cloud Build from
# infra/images and pulled by the nodes' identity.
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "pinecall"
  format        = "DOCKER"
  description   = "Pinecall's container images (infra/images)"
}

# What the operator reads after an apply: where each machine is, and what the server's env file is
# told (runtime/docs/the-runtime-cli.md, "A server that carries production").
output "address" {
  description = "The server's public address, which every name points at."
  value       = local.address
}

output "machines" {
  description = "Each machine's name: `gcloud compute ssh --tunnel-through-iap <name>` opens a shell on it."
  value = merge(
    { server = google_compute_instance.server.name },
    var.apps ? { apps = google_compute_instance.apps[0].name } : {},
  )
}

output "env" {
  description = "Lines of the server's env file that say what Terraform made."
  value = {
    PINECALL_BACKUP_URL    = "gs://${google_storage_bucket.postgres.name}/postgres"
    PINECALL_SIP_RTP_PORTS = var.rtp_ports
    PINECALL_PAGES_DOMAIN  = var.pages
  }
}

output "registry" {
  description = "The registry both machines are signed in to as their own service account."
  value       = local.registry
}

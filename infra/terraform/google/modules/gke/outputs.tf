output "cluster" {
  value = google_container_cluster.this.name
}

output "location" {
  value = google_container_cluster.this.location
}

output "nodes_service_account" {
  value = google_service_account.nodes.email
}

# What Helm reaches the cluster at: known in a plan whenever the cluster is only updated in place,
# so a change to the cluster never makes the addons' releases look new.
output "endpoint" {
  value = google_container_cluster.this.endpoint
}

output "ca_certificate" {
  value = google_container_cluster.this.master_auth[0].cluster_ca_certificate
}

# The pool a Kubernetes ServiceAccount is named in when it acts as a Google identity. Read from
# the cluster, so whoever binds one waits for the cluster by needing this, not by being told to.
output "workload_pool" {
  value = google_container_cluster.this.workload_identity_config[0].workload_pool
}

output "media_tag" {
  value = local.media_tag
}

# What a node may do as itself: write its logs and metrics, pull the cluster's images. Pods act
# as their own identities (Workload Identity), never as the node.
resource "google_service_account" "nodes" {
  account_id   = "pinecall-gke-${var.name}"
  display_name = "Pinecall GKE nodes, ${var.name}"
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
  ])
  project = var.project
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_container_node_pool" "core" {
  name       = "core"
  cluster    = google_container_cluster.this.id
  location   = var.zone
  node_count = var.core_nodes

  node_config {
    machine_type    = var.core_type
    disk_type       = "pd-balanced"
    disk_size_gb    = 50
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = { "pinecall.io/pool" = "core" }
    tags            = ["pinecall-gke-${var.name}", "pinecall-gke-core"]
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# A world's media: its LiveKit and its SIP on the node's own network, and its core workers. The
# taint keeps every other world's pod off; kubeip gives each node its world's static address
# (modules/edge), which LiveKit and SIP announce.
resource "google_container_node_pool" "media" {
  for_each = var.media_type
  name     = "media-${each.key}"
  cluster  = google_container_cluster.this.id
  location = var.zone
  # One: LiveKit and SIP hold the node's ports and announce the world's one address.
  node_count = 1

  node_config {
    machine_type    = each.value
    disk_type       = "pd-balanced"
    disk_size_gb    = 50
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = { "pinecall.io/pool" = "media-${each.key}" }
    tags            = ["pinecall-gke-${var.name}", local.media_tag]
    taint {
      key    = "pinecall.io/pool"
      value  = "media-${each.key}"
      effect = "NO_SCHEDULE"
    }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# A world's calls past its core workers (the taint keeps everything else off); the cluster
# autoscaler adds a node when a worker pod has nowhere to go and removes one once its pods are
# gone, waiting out their grace period, so a call is never cut to shrink the pool. Each world's
# ceiling is its own: a sandbox burst never takes production's.
resource "google_container_node_pool" "workers" {
  for_each = var.workers_max
  name     = "workers-${each.key}"
  cluster  = google_container_cluster.this.id
  location = var.zone

  autoscaling {
    min_node_count = 0
    max_node_count = each.value
  }

  node_config {
    machine_type    = var.workers_type
    disk_type       = "pd-balanced"
    disk_size_gb    = 50
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = { "pinecall.io/pool" = "workers-${each.key}" }
    tags            = ["pinecall-gke-${var.name}", "pinecall-gke-workers"]
    taint {
      key    = "pinecall.io/pool"
      value  = "workers-${each.key}"
      effect = "NO_SCHEDULE"
    }
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

locals {
  # The network tag of every media node: the firewall's rules for media and SIP name it (modules/edge).
  media_tag = "pinecall-gke-media"
}

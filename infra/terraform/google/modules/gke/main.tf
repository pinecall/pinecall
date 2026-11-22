# A world's Kubernetes cluster on Google Cloud: zonal (the free tier covers one zonal cluster's
# fee), public nodes (LiveKit and SIP need the node's own address: LiveKit supports no private
# cluster), VPC-native on a subnet of its own, Workload Identity for every pod's Google access.
# A pool for what both worlds share (core: the gateways, Postgres, Redis, the box's services), and
# per world a media pool (its LiveKit, its SIP, its core workers, on an address of its own) and a
# workers pool the cluster autoscaler alone grows and shrinks, honouring a worker's grace period
# to drain its calls: a sandbox call never shares a machine with a production call.

resource "google_project_service" "container" {
  project            = var.project
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

resource "google_container_cluster" "this" {
  name                = "pinecall-${var.name}"
  location            = var.zone
  network             = data.google_compute_network.vpc.id
  subnetwork          = google_compute_subnetwork.nodes.id
  deletion_protection = var.deletion_protection

  # The node pools are this module's own; the default one goes at once.
  remove_default_node_pool = true
  initial_node_count       = 1

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project}.svc.id.goog"
  }

  # The Gateway API: the HTTPS load balancer charts/pinecall declares, with Certificate Manager's
  # certificate (issued by DNS before a name points here, modules/edge).
  gateway_api_config {
    channel = "CHANNEL_STANDARD"
  }

  # Upgrades of the control plane and the nodes only in the window, when calls are fewest.
  maintenance_policy {
    recurring_window {
      start_time = "2026-01-01T07:00:00Z"
      end_time   = "2026-01-01T11:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }

  depends_on = [google_project_service.container]
}

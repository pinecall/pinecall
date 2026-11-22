data "google_compute_network" "vpc" {
  name = var.network
}

resource "google_compute_subnetwork" "nodes" {
  name          = "pinecall-gke-${var.name}"
  region        = var.region
  network       = data.google_compute_network.vpc.id
  ip_cidr_range = var.nodes_range
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_range
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_range
  }
  private_ip_google_access = true
}

# The nodes' way out when one has no address of its own: a node kubeip took a static address from
# is left with none until it is given one (production's core node, 2026-10-04: every vendor's call
# from the gateways timed out for 23 minutes). A node with its own address keeps going out by it;
# the NAT serves this cluster's subnet alone, never the VPC's other machines.
resource "google_compute_router" "nodes" {
  name    = "pinecall-gke-${var.name}"
  region  = var.region
  network = data.google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nodes" {
  name                               = "pinecall-gke-${var.name}"
  router                             = google_compute_router.nodes.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.nodes.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

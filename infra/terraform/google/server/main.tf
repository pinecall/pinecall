# The network and what reaches each machine. A network of its own with one subnet: both machines
# hold public addresses and no NAT is paid for; what reaches a machine is its firewall rules' to
# say, by its tag. Nobody opens port 22 to the world: a shell is opened through Identity-Aware
# Proxy as the operator's own Google login (`gcloud compute ssh --tunnel-through-iap`).

resource "google_compute_network" "this" {
  name                    = "pinecall-${var.name}-server"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "this" {
  name          = "pinecall-${var.name}-server"
  network       = google_compute_network.this.id
  region        = var.region
  ip_cidr_range = var.range
}

locals {
  server_tag = "pinecall-${var.name}-server"
  apps_tag   = "pinecall-${var.name}-server-apps"
}

# Caddy's two ports (Let's Encrypt proves a name on :80), LiveKit's media and SIP's audio: open to
# anyone, as a caller's network is nobody's to know.
resource "google_compute_firewall" "open" {
  name          = "pinecall-${var.name}-server-open"
  network       = google_compute_network.this.self_link
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [local.server_tag]
  allow {
    protocol = "tcp"
    ports    = ["80", "443", "7881"]
  }
  allow {
    protocol = "udp"
    ports    = ["443", "7882", var.rtp_ports]
  }
}

# 5060 from the carriers' networks and from the server's own address: a call the runtime rings on
# itself (a developer's ring dialled on to the sandbox, a simulated caller over SIP) leaves by it
# and comes back to it. A network with no rule for a port refuses it: nothing denies after.
resource "google_compute_firewall" "sip" {
  name          = "pinecall-${var.name}-server-sip"
  network       = google_compute_network.this.self_link
  direction     = "INGRESS"
  source_ranges = concat(var.sip_sources, ["${local.address}/32"])
  target_tags   = [local.server_tag]
  allow {
    protocol = "udp"
    ports    = ["5060"]
  }
  allow {
    protocol = "tcp"
    ports    = ["5060"]
  }
}

# Identity-Aware Proxy's own range, to both machines' port 22: the only way a shell is opened.
resource "google_compute_firewall" "shell" {
  name          = "pinecall-${var.name}-server-shell"
  network       = google_compute_network.this.self_link
  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = [local.server_tag, local.apps_tag]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

data "google_compute_network" "vpc" {
  name = var.network
}

resource "google_compute_firewall" "media" {
  name          = "pinecall-${var.name}-media"
  network       = data.google_compute_network.vpc.self_link
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.media_tag]
  allow {
    protocol = "udp"
    ports    = ["7882", var.rtp_ports]
  }
  allow {
    protocol = "tcp"
    ports    = ["7881"]
  }
}

# The carriers' networks, and production's own media address: a developer's ring at a production
# number is dialled on to the sandbox's SIP from there (docs/telephony.md, "A developer's own phone").
resource "google_compute_firewall" "sip" {
  count         = length(var.sip_sources) > 0 ? 1 : 0
  name          = "pinecall-${var.name}-sip"
  network       = data.google_compute_network.vpc.self_link
  direction     = "INGRESS"
  priority      = 500
  source_ranges = concat(var.sip_sources, [for world, address in google_compute_address.media : "${address.address}/32" if world == "production"])
  target_tags   = [var.media_tag]
  allow {
    protocol = "udp"
    ports    = ["5060"]
  }
  allow {
    protocol = "tcp"
    ports    = ["5060"]
  }
}

resource "google_compute_firewall" "sip_deny" {
  name          = "pinecall-${var.name}-sip-deny"
  network       = data.google_compute_network.vpc.self_link
  direction     = "INGRESS"
  priority      = 600
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.media_tag]
  deny {
    protocol = "udp"
    ports    = ["5060"]
  }
  deny {
    protocol = "tcp"
    ports    = ["5060"]
  }
}

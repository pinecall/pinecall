# A world's media address: kubeip (charts/pinecall) gives it to that world's media node by its
# label, and gives it again to the node that replaces it, so a carrier's trunk and a number's SDP
# name one address for good.
resource "google_compute_address" "media" {
  for_each = var.sip_names
  name     = lookup(var.kept_addresses, each.key, "pinecall-${var.name}-media-${each.key}")
  region   = var.region
  labels   = { pinecall-media = "${var.name}-${each.key}" }
}

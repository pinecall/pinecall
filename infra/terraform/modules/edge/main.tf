# Where a cluster meets the world: the global address its Gateway serves the name on; each world's
# media address, static, which its SIP and its LiveKit's media are reached at under the world's SIP
# name (Google's HTTPS load balancer carries no UDP); the names in Route 53 (the zone's other
# records are other repositories'); and the media nodes' ports. LiveKit's media and SIP's RTP are
# open to anyone; 5060 only from the networks named (the carriers'), everyone else's denied after.

resource "google_compute_global_address" "ingress" {
  name = "pinecall-${var.name}-ingress"
}

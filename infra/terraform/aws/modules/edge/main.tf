# Where a cluster meets the world on AWS. The names are served by an Application Load Balancer the
# load balancer controller makes for the chart's Gateway (charts/edge), with a certificate of
# Certificate Manager for each name, proved by DNS before the name points here; each env's media
# address is an Elastic IP, which its SIP and its LiveKit's media are reached at under the env's SIP
# name (the load balancer carries no UDP); the names are records of Route 53 (the zone's other
# records are other repositories'); and the media nodes' ports are two kinds of security group.
# LiveKit's media and SIP's RTP are open to anyone; 5060 only from the networks named (the
# carriers'): a security group refuses what it does not name, so nothing denies after.

data "aws_route53_zone" "zone" {
  name = var.zone
}

# An env's media address: kubeip (charts/pinecall) gives it to that env's media node by its tag,
# and gives it again to the node that replaces it, so a carrier's trunk and a number's SDP name one
# address for good.
resource "aws_eip" "media" {
  for_each = var.sip_names
  domain   = "vpc"
  tags = {
    Name           = "pinecall-${var.name}-media-${each.key}"
    pinecall-media = "${var.name}-${each.key}"
  }
}

resource "aws_security_group" "media" {
  name        = "pinecall-${var.name}-media"
  description = "Pinecall ${var.name}: a media node's LiveKit and RTP ports, open to callers"
  vpc_id      = var.vpc
  tags        = { Name = "pinecall-${var.name}-media" }
}

locals {
  rtp = [tonumber(split("-", var.rtp_ports)[0]), tonumber(split("-", var.rtp_ports)[1])]
  media_ports = {
    livekit-udp = { protocol = "udp", from = 7882, to = 7882 }
    livekit-tcp = { protocol = "tcp", from = 7881, to = 7881 }
    rtp         = { protocol = "udp", from = local.rtp[0], to = local.rtp[1] }
  }
}

resource "aws_vpc_security_group_ingress_rule" "media" {
  for_each          = local.media_ports
  security_group_id = aws_security_group.media.id
  description       = each.key
  ip_protocol       = each.value.protocol
  from_port         = each.value.from
  to_port           = each.value.to
  cidr_ipv4         = "0.0.0.0/0"
}

# The carriers' networks, and production's own media address: a developer's ring at a production
# number is dialled on to the sandbox's SIP from there (docs/telephony.md, "A developer's own
# phone"). A group a protocol: a security group holds sixty rules, and one for both would be full
# at thirty networks.

resource "aws_security_group" "sip" {
  for_each    = toset(["udp", "tcp"])
  name        = "pinecall-${var.name}-sip-${each.key}"
  description = "Pinecall ${var.name}: 5060/${each.key} from the carriers' networks alone"
  vpc_id      = var.vpc
  tags        = { Name = "pinecall-${var.name}-sip-${each.key}" }
}

resource "aws_vpc_security_group_ingress_rule" "sip" {
  for_each          = { for pair in setproduct(["udp", "tcp"], toset(var.sip_sources)) : "${pair[0]} ${pair[1]}" => pair }
  security_group_id = aws_security_group.sip[each.value[0]].id
  ip_protocol       = each.value[0]
  from_port         = 5060
  to_port           = 5060
  cidr_ipv4         = strcontains(each.value[1], ":") ? null : each.value[1]
  cidr_ipv6         = strcontains(each.value[1], ":") ? each.value[1] : null
}

# Production's own media address, where there is a production: named apart from the carriers',
# since a plan knows their networks and not yet this address.
resource "aws_vpc_security_group_ingress_rule" "sip_from_production" {
  for_each          = contains(keys(var.sip_names), "production") ? toset(["udp", "tcp"]) : toset([])
  security_group_id = aws_security_group.sip[each.key].id
  description       = "production's media address: a developer's ring dialled on"
  ip_protocol       = each.key
  from_port         = 5060
  to_port           = 5060
  cidr_ipv4         = "${aws_eip.media["production"].public_ip}/32"
}

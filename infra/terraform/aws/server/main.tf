# The network and what reaches each machine. One public subnet: both machines hold public
# addresses and no NAT gateway is paid for; what reaches a machine is its security group's to say,
# and a security group refuses what it does not name. Nobody signs in over SSH: a session is opened
# through Systems Manager as the operator's own AWS login (machines.tf), so no port 22 is open.

data "aws_caller_identity" "this" {}

resource "aws_vpc" "this" {
  cidr_block           = var.range
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "pinecall-${var.name}-server" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "pinecall-${var.name}-server" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "pinecall-${var.name}-server" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  availability_zone       = var.zone
  cidr_block              = var.range
  map_public_ip_on_launch = true
  tags                    = { Name = "pinecall-${var.name}-server" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# EC2 takes no apostrophe in the description of a security group or of a rule: each is said without one.
resource "aws_security_group" "server" {
  name        = "pinecall-${var.name}-server"
  description = "Pinecall ${var.name}: the proxy and the media of the server, open to callers"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "pinecall-${var.name}-server" }
}

locals {
  rtp = [tonumber(split("-", var.rtp_ports)[0]), tonumber(split("-", var.rtp_ports)[1])]
  # Caddy's two ports (Let's Encrypt proves a name on :80), LiveKit's media and SIP's audio: open to
  # anyone, as a caller's network is nobody's to know.
  open_ports = {
    http        = { protocol = "tcp", from = 80, to = 80 }
    https       = { protocol = "tcp", from = 443, to = 443 }
    https-udp   = { protocol = "udp", from = 443, to = 443 }
    livekit-tcp = { protocol = "tcp", from = 7881, to = 7881 }
    livekit-udp = { protocol = "udp", from = 7882, to = 7882 }
    rtp         = { protocol = "udp", from = local.rtp[0], to = local.rtp[1] }
  }
}

resource "aws_vpc_security_group_ingress_rule" "open" {
  for_each          = local.open_ports
  security_group_id = aws_security_group.server.id
  description       = each.key
  ip_protocol       = each.value.protocol
  from_port         = each.value.from
  to_port           = each.value.to
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "server" {
  security_group_id = aws_security_group.server.id
  description       = "anywhere: the vendors, the carriers, the registries"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# 5060 from the carriers' networks alone. A group a protocol: a security group holds sixty rules,
# and one for both would be full at thirty networks.
resource "aws_security_group" "sip" {
  for_each    = toset(["udp", "tcp"])
  name        = "pinecall-${var.name}-server-sip-${each.key}"
  description = "Pinecall ${var.name}: 5060/${each.key} of the server from the networks of the carriers alone"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "pinecall-${var.name}-server-sip-${each.key}" }
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

# The server's own address: a call the runtime rings on itself (a developer's ring dialled on to the
# sandbox, a simulated caller over SIP) leaves by it and comes back to it.
resource "aws_vpc_security_group_ingress_rule" "sip_from_itself" {
  for_each          = toset(["udp", "tcp"])
  security_group_id = aws_security_group.sip[each.key].id
  description       = "the address of the server itself"
  ip_protocol       = each.key
  from_port         = 5060
  to_port           = 5060
  cidr_ipv4         = "${local.address.public_ip}/32"
}

# The apps' machine answers nobody: its runners and its apps call the server by its public name.
resource "aws_security_group" "apps" {
  count       = var.apps ? 1 : 0
  name        = "pinecall-${var.name}-server-apps"
  description = "Pinecall ${var.name}: the machine of the hosted apps, which nothing reaches"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "pinecall-${var.name}-server-apps" }
}

resource "aws_vpc_security_group_egress_rule" "apps" {
  count             = var.apps ? 1 : 0
  security_group_id = aws_security_group.apps[0].id
  description       = "anywhere: the server by its name, the registries an app installs from"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

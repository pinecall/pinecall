# The cluster's network: a VPC of its own with public subnets alone. The nodes hold public
# addresses, as they do on Google Cloud (LiveKit and SIP need the node's own address, and LiveKit
# supports no private cluster), so there is no NAT gateway to pay for by the hour and by the
# gigabyte; what reaches a node is its security group's to say (modules/eks, modules/edge). Every
# node runs in the first zone, since a disk stays in its zone and traffic between zones is billed;
# the second zone exists because the control plane and the load balancer each ask for two. The load
# balancer has two small subnets to itself, so the addresses a request can arrive from are those
# and no pod's (the gateways believe X-Forwarded-For from them alone). The hosted apps' subnet is
# modules/hosting's, made in this VPC.

resource "aws_vpc" "this" {
  cidr_block           = var.range
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "pinecall-${var.name}" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "pinecall-${var.name}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "pinecall-${var.name}" }
}

locals {
  # A quarter of the range for the nodes and their pods (the VPC's own addresses: a pod takes one
  # of its node's subnet); a /24 each for the control plane's second zone and the load balancer's two.
  subnets = {
    nodes  = { zone = var.zones[0], range = cidrsubnet(var.range, 2, 0), balancer = false }
    second = { zone = var.zones[1], range = cidrsubnet(var.range, 8, 64), balancer = false }
    edge-a = { zone = var.zones[0], range = cidrsubnet(var.range, 8, 65), balancer = true }
    edge-b = { zone = var.zones[1], range = cidrsubnet(var.range, 8, 66), balancer = true }
  }
}

resource "aws_subnet" "public" {
  for_each                = local.subnets
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.zone
  cidr_block              = each.value.range
  map_public_ip_on_launch = true
  # The tag is where the load balancer controller puts an internet-facing load balancer.
  tags = merge(
    { Name = "pinecall-${var.name}-${each.key}" },
    each.value.balancer ? { "kubernetes.io/role/elb" = "1" } : {},
  )
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

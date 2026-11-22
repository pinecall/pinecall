output "vpc" {
  value = aws_vpc.this.id
}

output "range" {
  value = aws_vpc.this.cidr_block
}

# The control plane's two subnets, one a zone.
output "subnets" {
  value = [aws_subnet.public["nodes"].id, aws_subnet.public["second"].id]
}

# The load balancer's own two, and their ranges: every address a request reaches a gateway from.
output "balancer_subnets" {
  value = [aws_subnet.public["edge-a"].id, aws_subnet.public["edge-b"].id]
}

output "balancer_ranges" {
  value = [aws_subnet.public["edge-a"].cidr_block, aws_subnet.public["edge-b"].cidr_block]
}

# The nodes' subnet, where their pods take their addresses too.
output "nodes_subnet" {
  value = aws_subnet.public["nodes"].id
}

output "nodes_range" {
  value = aws_subnet.public["nodes"].cidr_block
}

output "zone" {
  value = var.zones[0]
}

# The route to the internet, for a subnet another module makes in this VPC (modules/hosting).
output "route_table" {
  value = aws_route_table.public.id
}

# The sixteenth of the range kept for the hosted apps' subnet.
output "hosting_range" {
  value = cidrsubnet(var.range, 4, 5)
}

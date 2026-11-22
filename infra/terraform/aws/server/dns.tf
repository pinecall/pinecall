# The names in Route 53: every one an A record to the server's one address, which outlives the
# machine that holds it. They start unpointed (`point_names`, `point_sip`): a server is set up and
# tried by its address first. A record that already exists is taken over in one change
# (`allow_overwrite`), so a name another deployment pointed elsewhere moves here with no moment in
# which it resolves to nothing; whoever held it before then forgets it and never removes it.
data "aws_route53_zone" "zone" {
  name = var.dns_zone
}

resource "aws_eip" "server" {
  count  = var.kept_address == null ? 1 : 0
  domain = "vpc"
  tags   = { Name = "pinecall-${var.name}-server" }
}

data "aws_eip" "kept" {
  count = var.kept_address == null ? 0 : 1
  id    = var.kept_address
}

locals {
  address = {
    id        = var.kept_address == null ? aws_eip.server[0].id : data.aws_eip.kept[0].id
    public_ip = var.kept_address == null ? aws_eip.server[0].public_ip : data.aws_eip.kept[0].public_ip
  }
  pointed = merge(
    var.point_names ? { for name in concat(var.names, var.services) : name => name } : {},
    var.point_names && var.pages != "" ? { pages = "*.${var.pages}" } : {},
    var.point_sip ? { for name in var.sip_names : name => name } : {},
  )
}

resource "aws_eip_association" "server" {
  allocation_id = local.address.id
  instance_id   = aws_instance.server.id
}

resource "aws_route53_record" "pointed" {
  for_each        = local.pointed
  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.value
  type            = "A"
  ttl             = 300
  allow_overwrite = true
  records         = [local.address.public_ip]
}

# The names in Route 53: every one an A record to the server's one address, which outlives the
# machine that holds it. They start unpointed (`point_names`, `point_sip`): a server is set up and
# tried by its address first. A record that already exists is taken over in one change
# (`allow_overwrite`), so a name another deployment pointed elsewhere moves here with no moment in
# which it resolves to nothing; whoever held it before then forgets it and never removes it.
data "aws_route53_zone" "zone" {
  name = var.dns_zone
}

resource "google_compute_address" "server" {
  count  = var.kept_address == null ? 1 : 0
  name   = "pinecall-${var.name}-server"
  region = var.region
}

data "google_compute_address" "kept" {
  count  = var.kept_address == null ? 0 : 1
  name   = var.kept_address
  region = var.region
}

locals {
  address = var.kept_address == null ? google_compute_address.server[0].address : data.google_compute_address.kept[0].address
  pointed = merge(
    var.point_names ? { for name in concat(var.names, var.services) : name => name } : {},
    var.point_names && var.pages != "" ? { pages = "*.${var.pages}" } : {},
    var.point_sip ? { for name in var.sip_names : name => name } : {},
  )
}

resource "aws_route53_record" "pointed" {
  for_each        = local.pointed
  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.value
  type            = "A"
  ttl             = 300
  allow_overwrite = true
  records         = [local.address]
}

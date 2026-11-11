# The names in Route 53: the worlds', the services', each world's SIP name, and the apps' pages under
# one wildcard (whose certificate is in certificates.tf).
data "aws_route53_zone" "zone" {
  name = var.zone
}

resource "aws_route53_record" "names" {
  for_each = var.point_names ? toset(var.names) : toset([])
  zone_id  = data.aws_route53_zone.zone.zone_id
  name     = each.value
  type     = "A"
  ttl      = 300
  records  = [google_compute_global_address.ingress.address]
}

resource "aws_route53_record" "services" {
  for_each = var.point_services ? toset(var.services) : toset([])
  zone_id  = data.aws_route53_zone.zone.zone_id
  name     = each.value
  type     = "A"
  ttl      = 300
  records  = [google_compute_global_address.ingress.address]
}

resource "aws_route53_record" "sip_names" {
  for_each = var.sip_names
  zone_id  = data.aws_route53_zone.zone.zone_id
  name     = each.value
  type     = "A"
  ttl      = 300
  records  = [google_compute_address.media[each.key].address]
}

resource "aws_route53_record" "pages" {
  count   = var.pages == "" ? 0 : 1
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = "*.${var.pages}"
  type    = "A"
  ttl     = 300
  records = [google_compute_global_address.ingress.address]
}

# The names in Route 53: the envs', the services', each env's SIP name, and the apps' pages under
# one wildcard. The load balancer is the chart's (charts/edge names it `load_balancer`, and the
# controller makes it when `make edge` runs), so it exists only after the first release: the names
# point at it once `point_names` says so, and until then a plan asks nothing about it. That is the
# order of a cutover too: the certificates issued, the front door released and tried by its own
# address, and only then the names moved. A record that already exists is taken over in one change
# (`allow_overwrite`), so a name that another stack pointed elsewhere moves here with no moment in
# which it resolves to nothing; whoever held it before then forgets it (`terraform state rm`), never
# removes it.

data "aws_lb" "ingress" {
  count = var.point_names || var.point_services ? 1 : 0
  name  = local.load_balancer
}

locals {
  load_balancer = "pinecall-${var.name}"
  pointed = merge(
    var.point_names ? { for name in var.names : name => name } : {},
    var.point_names && var.pages != "" ? { pages = "*.${var.pages}" } : {},
    var.point_services ? { for name in var.services : name => name } : {},
  )
}

resource "aws_route53_record" "pointed" {
  for_each        = local.pointed
  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.value
  type            = "A"
  allow_overwrite = true
  alias {
    name                   = data.aws_lb.ingress[0].dns_name
    zone_id                = data.aws_lb.ingress[0].zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "sip_names" {
  for_each        = var.point_sip ? var.sip_names : {}
  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.value
  type            = "A"
  ttl             = 300
  allow_overwrite = true
  records         = [aws_eip.media[each.key].public_ip]
}

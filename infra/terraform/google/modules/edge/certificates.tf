# Each name's HTTPS certificate, Google-managed and proved by DNS (a CNAME each in Route 53), so it
# is issued before the name points at the load balancer: a cutover moves a name onto a certificate
# already valid. One certificate a name, so adding or retiring a name never reissues another's.
# The chart's Gateway serves them through the map.
resource "google_project_service" "certificates" {
  service            = "certificatemanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_certificate_manager_dns_authorization" "names" {
  for_each   = toset(var.names)
  name       = "pinecall-${var.name}-${replace(each.value, ".", "-")}"
  domain     = each.value
  depends_on = [google_project_service.certificates]
}

resource "aws_route53_record" "authorizations" {
  for_each = google_certificate_manager_dns_authorization.names
  zone_id  = data.aws_route53_zone.zone.zone_id
  name     = each.value.dns_resource_record[0].name
  type     = each.value.dns_resource_record[0].type
  ttl      = 300
  records  = [each.value.dns_resource_record[0].data]
}

resource "google_certificate_manager_certificate" "each" {
  for_each = toset(var.names)
  name     = "pinecall-${var.name}-${replace(each.value, ".", "-")}"
  managed {
    domains            = [each.value]
    dns_authorizations = [google_certificate_manager_dns_authorization.names[each.value].id]
  }
}

resource "google_certificate_manager_certificate_map" "names" {
  name = "pinecall-${var.name}"
}

resource "google_certificate_manager_certificate_map_entry" "names" {
  for_each     = toset(var.names)
  name         = "pinecall-${var.name}-${replace(each.value, ".", "-")}"
  map          = google_certificate_manager_certificate_map.names.name
  hostname     = each.value
  certificates = [google_certificate_manager_certificate.each[each.value].id]
}

# Pinecall's own services at the same front door (notify, billing; their charts are their own
# repositories'): a certificate of their own in the same map, so adding one never reissues the
# worlds' certificate, which a name in use is served on.
resource "google_certificate_manager_dns_authorization" "services" {
  for_each   = toset(var.services)
  name       = "pinecall-${var.name}-${replace(each.value, ".", "-")}"
  domain     = each.value
  depends_on = [google_project_service.certificates]
}

resource "aws_route53_record" "service_authorizations" {
  for_each = google_certificate_manager_dns_authorization.services
  zone_id  = data.aws_route53_zone.zone.zone_id
  name     = each.value.dns_resource_record[0].name
  type     = each.value.dns_resource_record[0].type
  ttl      = 300
  records  = [each.value.dns_resource_record[0].data]
}

resource "google_certificate_manager_certificate" "services" {
  count = length(var.services) > 0 ? 1 : 0
  name  = "pinecall-${var.name}-services"
  managed {
    domains            = var.services
    dns_authorizations = [for authorization in google_certificate_manager_dns_authorization.services : authorization.id]
  }
}

resource "google_certificate_manager_certificate_map_entry" "services" {
  for_each     = toset(var.services)
  name         = "pinecall-${var.name}-${replace(each.value, ".", "-")}"
  map          = google_certificate_manager_certificate_map.names.name
  hostname     = each.value
  certificates = [google_certificate_manager_certificate.services[0].id]
}

# The apps' own pages: every name one label under `pages` (`<app>--<org>.<pages>`), served by the
# gateways at this front door. One wildcard certificate, proved by the domain's own authorization, and
# one wildcard record: a new app's page needs neither a certificate nor a record of its own.
resource "google_certificate_manager_dns_authorization" "pages" {
  count      = var.pages == "" ? 0 : 1
  name       = "pinecall-${var.name}-pages"
  domain     = var.pages
  depends_on = [google_project_service.certificates]
}

resource "aws_route53_record" "pages_authorization" {
  count   = var.pages == "" ? 0 : 1
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = google_certificate_manager_dns_authorization.pages[0].dns_resource_record[0].name
  type    = google_certificate_manager_dns_authorization.pages[0].dns_resource_record[0].type
  ttl     = 300
  records = [google_certificate_manager_dns_authorization.pages[0].dns_resource_record[0].data]
}

resource "google_certificate_manager_certificate" "pages" {
  count = var.pages == "" ? 0 : 1
  name  = "pinecall-${var.name}-pages"
  managed {
    domains            = ["*.${var.pages}"]
    dns_authorizations = [google_certificate_manager_dns_authorization.pages[0].id]
  }
}

resource "google_certificate_manager_certificate_map_entry" "pages" {
  count        = var.pages == "" ? 0 : 1
  name         = "pinecall-${var.name}-pages"
  map          = google_certificate_manager_certificate_map.names.name
  hostname     = "*.${var.pages}"
  certificates = [google_certificate_manager_certificate.pages[0].id]
}

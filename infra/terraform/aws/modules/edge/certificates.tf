# Each name's HTTPS certificate, AWS-managed and proved by DNS (a CNAME each in Route 53), so it is
# issued before the name points at the load balancer: a cutover moves a name onto a certificate
# already valid. One certificate a name, so adding or retiring a name never reissues another's; the
# services' share one, apart from the names', and the apps' pages take one wildcard. The chart's
# Gateway is given every one by its ARN (charts/edge, `ingress.aws.certificates`).

locals {
  certificates = merge(
    { for name in var.names : name => { domain = name, others = [] } },
    length(var.services) > 0 ? { services = { domain = var.services[0], others = slice(var.services, 1, length(var.services)) } } : {},
    var.pages == "" ? {} : { pages = { domain = "*.${var.pages}", others = [] } },
  )
  # Every proof, once: a wildcard and its own domain would ask for the same record twice.
  proofs = {
    for proof in flatten([
      for key, certificate in aws_acm_certificate.each : [
        for option in certificate.domain_validation_options : {
          name = option.resource_record_name, type = option.resource_record_type, value = option.resource_record_value
        }
      ]
    ]) : proof.name => proof...
  }
}

resource "aws_acm_certificate" "each" {
  for_each                  = local.certificates
  domain_name               = each.value.domain
  subject_alternative_names = each.value.others
  validation_method         = "DNS"
  tags                      = { Name = "pinecall-${var.name}-${replace(replace(each.key, ".", "-"), "*", "any")}" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "proofs" {
  for_each        = local.proofs
  zone_id         = data.aws_route53_zone.zone.zone_id
  name            = each.key
  type            = each.value[0].type
  ttl             = 300
  records         = [each.value[0].value]
  allow_overwrite = true
}

# Waited for: a Gateway given a certificate not yet issued serves nothing on its name.
resource "aws_acm_certificate_validation" "each" {
  for_each                = aws_acm_certificate.each
  certificate_arn         = each.value.arn
  validation_record_fqdns = [for option in each.value.domain_validation_options : option.resource_record_name]
  depends_on              = [aws_route53_record.proofs]
}

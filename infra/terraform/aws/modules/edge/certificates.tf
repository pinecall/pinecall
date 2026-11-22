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
  # Every domain a certificate names, by what a plan already knows of it (the certificate and the
  # domain): the record that proves it is known only once Certificate Manager has answered.
  proofs = merge([
    for key, certificate in local.certificates : {
      for domain in concat([certificate.domain], certificate.others) :
      "${key} ${domain}" => { certificate = key, domain = domain }
    }
  ]...)
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
  name            = one([for option in aws_acm_certificate.each[each.value.certificate].domain_validation_options : option.resource_record_name if option.domain_name == each.value.domain])
  type            = one([for option in aws_acm_certificate.each[each.value.certificate].domain_validation_options : option.resource_record_type if option.domain_name == each.value.domain])
  ttl             = 300
  records         = [one([for option in aws_acm_certificate.each[each.value.certificate].domain_validation_options : option.resource_record_value if option.domain_name == each.value.domain])]
  allow_overwrite = true
}

# Waited for: a Gateway given a certificate not yet issued serves nothing on its name.
resource "aws_acm_certificate_validation" "each" {
  for_each                = aws_acm_certificate.each
  certificate_arn         = each.value.arn
  validation_record_fqdns = [for option in each.value.domain_validation_options : option.resource_record_name]
  depends_on              = [aws_route53_record.proofs]
}

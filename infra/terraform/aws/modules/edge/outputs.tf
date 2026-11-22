# The name the chart gives its load balancer, which the names' records then find it by.
output "load_balancer" {
  value = local.load_balancer
}

# Every certificate's ARN, the first name's first: the Gateway's default.
output "certificates" {
  value = concat(
    [for name in var.names : aws_acm_certificate_validation.each[name].certificate_arn],
    [for key, validation in aws_acm_certificate_validation.each : validation.certificate_arn if !contains(var.names, key)],
  )
}

output "media_addresses" {
  value = { for env, address in aws_eip.media : env => address.public_ip }
}

# What a media node carries besides the cluster's own group.
output "media_security_groups" {
  value = concat([aws_security_group.media.id], [for group in aws_security_group.sip : group.id])
}

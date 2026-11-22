# What the operator reads after an apply: where each machine is, and what the server's env file is
# told (runtime/docs/the-runtime-cli.md, "A server that carries production").
output "address" {
  description = "The server's public address, which every name points at."
  value       = local.address.public_ip
}

output "machines" {
  description = "Each machine's instance id: `aws ssm start-session --target <id>` opens a shell on it."
  value       = merge({ server = aws_instance.server.id }, var.apps ? { apps = aws_instance.apps[0].id } : {})
}

output "env" {
  description = "Lines of the server's env file that say what Terraform made."
  value = {
    PINECALL_BACKUP_URL    = "s3://${aws_s3_bucket.postgres.bucket}/postgres"
    PINECALL_SIP_RTP_PORTS = var.rtp_ports
    PINECALL_PAGES_DOMAIN  = var.pages
  }
}

output "registry" {
  description = "The registry both machines are signed in to as their own role."
  value       = local.registry
}

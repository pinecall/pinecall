# The deployment's own secrets, each a name here and a value the operator puts: a server is one disk,
# and the keys its database is sealed and signed with must outlive it. Nothing reads them while the
# server runs (its env file holds what it runs on); a server made again begins its env file from them.
resource "aws_secretsmanager_secret" "kept" {
  for_each = toset(var.keeps_secrets)
  name     = each.key
}

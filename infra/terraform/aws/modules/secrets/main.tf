# A cluster's own secrets in the shapes the runtime reads, kept in AWS Secrets Manager and synced
# into the cluster by External Secrets Operator acting as a role that reads these alone
# (modules/identity). Most are drawn here once, and are in Terraform's state, the private, versioned
# bucket of bootstrap/; nothing prints them. Those named in `given` are the operator's to put, once,
# piped (`aws secretsmanager put-secret-value --secret-id <id> --secret-string file:///dev/stdin`):
# a value that already exists elsewhere (the vault key every sealed row of a database is under, an
# access key made by hand) and that Terraform's state never holds. The names and the shapes are
# terraform/google/modules/secrets', one for one: a chart reads <prefix><name> on either cloud.

# A Fernet key: 32 random bytes, URL-safe base64 with its padding.
resource "random_id" "vault" {
  byte_length = 32
}

resource "random_id" "ops" {
  byte_length = 24
}

# The gateway's own signing key (PINECALL_TOKEN_KEY): no worker and no LiveKit holds it.
resource "random_password" "token" {
  length  = 48
  special = false
}

resource "random_id" "livekit_key" {
  byte_length = 6
}

resource "random_password" "livekit_secret" {
  length  = 43
  special = false
}

resource "random_id" "redis" {
  byte_length = 24
}

# Each env's fleet key: the gateway knows it by its settings, and the env's workers and KEDA knock
# with it. A cluster whose workers already hold one puts that one instead (`given`).
resource "random_id" "fleet" {
  for_each    = toset(["production", "sandbox"])
  byte_length = 32
}

# The password of the gateway's database role (charts/postgres's managed role pinecall_app): it
# reads and writes rows and changes no table. Letters and digits alone: it rides a URI.
resource "random_password" "postgres_app" {
  length  = 40
  special = false
}

locals {
  drawn = {
    "vault-key"             = "${random_id.vault.b64_url}="
    "ops-key"               = "pc_ops_${random_id.ops.hex}"
    "token-key"             = random_password.token.result
    "livekit-api-key"       = "API${random_id.livekit_key.hex}"
    "livekit-api-secret"    = random_password.livekit_secret.result
    "redis-password"        = random_id.redis.hex
    "postgres-app-password" = random_password.postgres_app.result
    "fleet-key-production"  = "pc_fleet_${random_id.fleet["production"].hex}"
    "fleet-key-sandbox"     = "pc_fleet_${random_id.fleet["sandbox"].hex}"
  }
  values = { for name, value in local.drawn : name => value if !contains(var.given, name) }
  names  = toset(concat(keys(local.values), var.given))
  # External Secrets' own ServiceAccount in the cluster (its chart's name and namespace), which
  # reads the store as the role below.
  reader = { name = "external-secrets", namespace = "external-secrets" }
}

# A secret deleted is kept `recovery_days` before it is gone, and its name with it: zero for a
# cluster made for a proof and destroyed after it, which is made again under the same names.
resource "aws_secretsmanager_secret" "this" {
  for_each                = local.names
  name                    = "pinecall-${var.name}-${each.key}"
  recovery_window_in_days = var.recovery_days
}

resource "aws_secretsmanager_secret_version" "this" {
  for_each      = local.values
  secret_id     = aws_secretsmanager_secret.this[each.key].id
  secret_string = each.value
}

data "aws_iam_policy_document" "sync" {
  statement {
    sid       = "ReadTheClustersSecrets"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [for secret in aws_secretsmanager_secret.this : secret.arn]
  }
}

# External Secrets Operator's identity in the cluster reads these secrets and nothing else.
module "sync" {
  source           = "../identity"
  name             = "pinecall-${var.name}-secrets"
  description      = "Pinecall ${var.name}: External Secrets Operator"
  issuer           = var.issuer
  service_accounts = ["${local.reader.namespace}/${local.reader.name}"]
}

resource "aws_iam_role_policy" "sync" {
  name   = "read-the-clusters-secrets"
  role   = module.sync.name
  policy = data.aws_iam_policy_document.sync.json
}

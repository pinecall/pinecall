# The deployment's own secrets, each an id here and a value the operator puts: a server is one disk,
# and the keys its database is sealed and signed with must outlive it. Nothing reads them while the
# server runs (its env file holds what it runs on); a server made again begins its env file from them.
resource "google_secret_manager_secret" "kept" {
  for_each  = toset(var.keeps_secrets)
  secret_id = each.key
  replication {
    auto {}
  }
}

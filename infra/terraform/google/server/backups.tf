# Where the server's Postgres keeps its past: its WAL and its nightly base backups, sent by the
# server itself (`PINECALL_BACKUP_URL`, runtime/docs/the-runtime-cli.md) as the machine's own
# service account. The backups' own retention deletes what is older than its window, so no rule here
# expires a live object: one of its own could delete a WAL file a kept base backup still needs.
data "google_project" "this" {}

resource "google_storage_bucket" "postgres" {
  name                        = "pinecall-${var.name}-server-postgres-${data.google_project.this.number}"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  # The server can delete what it wrote: a deleted object is kept seven days as an old version.
  versioning {
    enabled = true
  }
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "postgres" {
  bucket = google_storage_bucket.postgres.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.machine["server"].email}"
}

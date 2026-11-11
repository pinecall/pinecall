# What the project holds for every cluster in it: the registry the images live in and the identity
# Cloud Build builds them as (`make image`). Each cluster (cluster/, once per ENV) is made beside
# these.
#
# The registry and the builds' identity were modules of one caller each until 2026-11-12; they are
# this root's own files now, and the state follows by the moves below.

moved {
  from = module.registry.google_artifact_registry_repository.images
  to   = google_artifact_registry_repository.images
}

moved {
  from = module.build.google_service_account.build
  to   = google_service_account.build
}

moved {
  from = module.build.google_project_iam_member.build
  to   = google_project_iam_member.build
}

moved {
  from = module.build.google_storage_bucket_iam_member.source
  to   = google_storage_bucket_iam_member.source
}

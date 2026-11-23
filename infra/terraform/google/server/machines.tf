# The two machines. Ubuntu's current long-term release: a machine that runs keeps the image it was
# made from, and its packages are its own to update. What a machine needs before the runtime is put
# on it is installed as it first starts (Docker and its compose plugin, signed in to the registry
# as the machine's service account, uv; on the apps' machine Node too); the runtime itself is put on
# it by `infra/server/install` and `infra/server/runners`, run in a shell opened through
# Identity-Aware Proxy.

locals {
  registry = "${var.region}-docker.pkg.dev"
  # What a machine installs as it first starts, by its kind: the user everything runs as, Docker
  # signed in to the registry as the machine's service account (a token read from the machine's own
  # metadata each time), uv, and on the apps' machine Node, which an app's install and process need.
  first_start = { for kind in ["server", "apps"] : kind => <<-EOT
    #!/bin/bash
    set -euo pipefail
    [ -f /var/lib/pinecall-first-start ] && exit 0
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2 curl ca-certificates unzip
    id pinecall >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups docker pinecall
    loginctl enable-linger pinecall
    cat > /usr/local/bin/docker-credential-metadata <<'HELPER'
    #!/bin/bash
    # Docker's credential helper for Artifact Registry: the machine's own token, read when asked.
    [ "$1" = get ] || exit 0
    token=$(curl -fsS -H "Metadata-Flavor: Google" \
      "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
      | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
    printf '{"Username": "oauth2accesstoken", "Secret": "%s"}\n' "$token"
    HELPER
    chmod 0755 /usr/local/bin/docker-credential-metadata
    install -d -o pinecall -g pinecall -m 0700 /home/pinecall/.docker
    echo '{"credHelpers": {"${local.registry}": "metadata"}}' > /home/pinecall/.docker/config.json
    chown pinecall:pinecall /home/pinecall/.docker/config.json
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
    %{if kind == "apps"}
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
    apt-get install -y -qq nodejs
    %{endif}
    touch /var/lib/pinecall-first-start
  EOT
  }
  kinds = toset(var.apps ? ["server", "apps"] : ["server"])
}

# What each machine acts as. Either pulls the registry's images and writes its logs; the server
# alone writes the backups' bucket (backups.tf) and reads the deployment's secrets (secrets.tf).
resource "google_service_account" "machine" {
  for_each     = local.kinds
  account_id   = "pinecall-${var.name}-srv-${each.key}"
  display_name = "Pinecall ${var.name}: what the ${each.key} machine acts as"
}

resource "google_project_iam_member" "machine" {
  for_each = { for pair in setproduct(local.kinds, ["roles/artifactregistry.reader", "roles/logging.logWriter"]) : "${pair[0]} ${pair[1]}" => pair }
  project  = var.project
  role     = each.value[1]
  member   = "serviceAccount:${google_service_account.machine[each.value[0]].email}"
}

# The server alone reads the deployment's secrets and another's named; the apps' machine, which
# runs other people's code, reads only the ones named for it, and by default none.
resource "google_secret_manager_secret_iam_member" "reads" {
  for_each  = toset(concat(var.reads_secrets, [for secret in google_secret_manager_secret.kept : secret.secret_id]))
  secret_id = each.key
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.machine["server"].email}"
}

resource "google_secret_manager_secret_iam_member" "apps_reads" {
  for_each  = toset(var.apps ? var.apps_reads_secrets : [])
  secret_id = google_secret_manager_secret.kept[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.machine["apps"].email}"
}

resource "google_compute_instance" "server" {
  name         = "pinecall-${var.name}-server"
  machine_type = var.machines.server
  zone         = var.zone
  tags         = [local.server_tag]
  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = var.machines.server_disk
      type  = "pd-balanced"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.this.id
    access_config {
      nat_ip = local.address
    }
  }
  service_account {
    email  = google_service_account.machine["server"].email
    scopes = ["cloud-platform"]
  }
  metadata = {
    enable-oslogin = "TRUE"
    startup-script = local.first_start["server"]
  }
  allow_stopping_for_update = true
  # The machine that runs is not made again because Ubuntu published an image.
  lifecycle {
    ignore_changes = [boot_disk[0].initialize_params[0].image]
  }
}

resource "google_compute_instance" "apps" {
  count        = var.apps ? 1 : 0
  name         = "pinecall-${var.name}-server-apps"
  machine_type = var.machines.apps
  zone         = var.zone
  tags         = [local.apps_tag]
  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = var.machines.apps_disk
      type  = "pd-balanced"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.this.id
    access_config {}
  }
  service_account {
    email  = google_service_account.machine["apps"].email
    scopes = ["cloud-platform"]
  }
  metadata = {
    enable-oslogin = "TRUE"
    startup-script = local.first_start["apps"]
  }
  allow_stopping_for_update = true
  lifecycle {
    ignore_changes = [boot_disk[0].initialize_params[0].image]
  }
}

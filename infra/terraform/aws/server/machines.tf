# The two machines. Ubuntu's current long-term release, found once: a machine that runs keeps the
# image it was made from, and its packages are its own to update. What a machine needs before the
# runtime is put on it is installed as it first starts (Docker and its compose plugin, the helper
# that signs Docker in to the registry as the machine's role, uv; on the apps' machine Node too);
# the runtime itself is put on it by `infra/server/install` and `infra/server/runners`, run in a
# session of Systems Manager.

data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

locals {
  registry = "${data.aws_caller_identity.this.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  # What a machine installs as it first starts, by its kind: the user everything runs as, Docker
  # signed in to the registry as the machine's role, uv, and on the apps' machine Node, which an
  # app's install and its process need.
  first_start = { for kind in ["server", "apps"] : kind => <<-EOT
    #!/bin/bash
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2 amazon-ecr-credential-helper curl ca-certificates unzip
    id pinecall >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups docker pinecall
    loginctl enable-linger pinecall
    install -d -o pinecall -g pinecall -m 0700 /home/pinecall/.docker
    echo '{"credHelpers": {"${local.registry}": "ecr-login"}}' > /home/pinecall/.docker/config.json
    chown pinecall:pinecall /home/pinecall/.docker/config.json
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
    %{if kind == "apps"}
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
    apt-get install -y -qq nodejs
    %{endif}
  EOT
  }
}

data "aws_iam_policy_document" "machine" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# What either machine may do as itself: be reached by a session of Systems Manager, pull the
# registry's images, and read the secrets under the prefix named, if one is.
data "aws_iam_policy_document" "both" {
  statement {
    sid       = "SignInToTheRegistry"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "PullItsImages"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
    resources = ["arn:aws:ecr:${var.region}:${data.aws_caller_identity.this.account_id}:repository/pinecall/*"]
  }
  dynamic "statement" {
    for_each = var.reads_secrets == "" ? [] : [var.reads_secrets]
    content {
      sid       = "ReadTheSecretsNamed"
      actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      resources = ["arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.this.account_id}:secret:${statement.value}*"]
    }
  }
}

# The server alone writes the backups' bucket.
data "aws_iam_policy_document" "backups" {
  statement {
    sid       = "ListTheBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.postgres.arn]
  }
  statement {
    sid       = "ReadAndWriteItsObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.postgres.arn}/*"]
  }
}

resource "aws_iam_role" "machine" {
  for_each           = toset(var.apps ? ["server", "apps"] : ["server"])
  name               = "pinecall-${var.name}-server-${each.key}"
  description        = "Pinecall ${var.name}: what the ${each.key} machine acts as"
  assume_role_policy = data.aws_iam_policy_document.machine.json
}

resource "aws_iam_role_policy_attachment" "session" {
  for_each   = aws_iam_role.machine
  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "both" {
  for_each = aws_iam_role.machine
  name     = "registry-and-secrets"
  role     = each.value.name
  policy   = data.aws_iam_policy_document.both.json
}

resource "aws_iam_role_policy" "backups" {
  name   = "its-own-bucket"
  role   = aws_iam_role.machine["server"].name
  policy = data.aws_iam_policy_document.backups.json
}

resource "aws_iam_instance_profile" "machine" {
  for_each = aws_iam_role.machine
  name     = each.value.name
  role     = each.value.name
}

resource "aws_instance" "server" {
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.machines.server
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.server.id, aws_security_group.sip["udp"].id, aws_security_group.sip["tcp"].id]
  iam_instance_profile   = aws_iam_instance_profile.machine["server"].name
  user_data              = local.first_start["server"]
  # Postgres runs in a container on Docker's bridge: a second hop for the address a role is read at.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_type = "gp3"
    volume_size = var.machines.server_disk
    encrypted   = true
    tags        = { Name = "pinecall-${var.name}-server" }
  }
  tags = { Name = "pinecall-${var.name}-server" }
  # The machine that runs is not made again because Ubuntu published an image or this file's first
  # start changed: both are for the next machine.
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_instance" "apps" {
  count                  = var.apps ? 1 : 0
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.machines.apps
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.apps[0].id]
  iam_instance_profile   = aws_iam_instance_profile.machine["apps"].name
  user_data              = local.first_start["apps"]
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_type = "gp3"
    volume_size = var.machines.apps_disk
    encrypted   = true
    tags        = { Name = "pinecall-${var.name}-server-apps" }
  }
  tags = { Name = "pinecall-${var.name}-server-apps" }
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

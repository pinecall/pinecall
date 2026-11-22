# Who builds infra's images: a CodeBuild project with a role of its own. It reads the source `make
# image` uploads, pushes to the registry's repositories, and writes its logs; nothing else. The
# steps are infra/images/buildspec.yaml, kept in the project so a context that holds no file of the
# repository (a suite's, an image's own folder) is built by the same ones.

data "aws_caller_identity" "this" {}

# Where `make image` puts a build's context; a week later it is gone.
resource "aws_s3_bucket" "source" {
  bucket        = "pinecall-build-${data.aws_caller_identity.this.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "source" {
  bucket                  = aws_s3_bucket.source.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "source" {
  bucket = aws_s3_bucket.source.id
  rule {
    id     = "a-week"
    status = "Enabled"
    filter {}
    expiration {
      days = 7
    }
  }
}

resource "aws_cloudwatch_log_group" "build" {
  name              = "/pinecall/build"
  retention_in_days = 30
}

data "aws_iam_policy_document" "build_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "build" {
  statement {
    sid       = "ReadTheSource"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.source.arn}/*"]
  }
  statement {
    sid       = "WriteItsLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.build.arn}:*"]
  }
  # The login token is the account's, asked of no repository.
  statement {
    sid       = "SignInToTheRegistry"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "PushToItsRepositories"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [for repository in aws_ecr_repository.images : repository.arn]
  }
}

resource "aws_iam_role" "build" {
  name               = "pinecall-build"
  description        = "Pinecall image builds (CodeBuild)"
  assume_role_policy = data.aws_iam_policy_document.build_trust.json
}

resource "aws_iam_role_policy" "build" {
  name   = "build"
  role   = aws_iam_role.build.id
  policy = data.aws_iam_policy_document.build.json
}

resource "aws_codebuild_project" "image" {
  name         = "pinecall-image"
  description  = "One image of infra/images, built from the context `make image` uploads and pushed to the registry"
  service_role = aws_iam_role.build.arn
  # The runtime's image fetches two models and builds the console: under ten minutes; an hour is a build that hangs.
  build_timeout = 60

  # Each build names its own context (`--source-location-override`); this one is never read.
  source {
    type      = "S3"
    location  = "${aws_s3_bucket.source.bucket}/none.zip"
    buildspec = file("${path.module}/../../../images/buildspec.yaml")
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    type         = "LINUX_CONTAINER"
    compute_type = "BUILD_GENERAL1_LARGE"
    image        = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
    # docker build needs the daemon, which CodeBuild starts only in a privileged container.
    privileged_mode = true
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.build.name
    }
  }
}

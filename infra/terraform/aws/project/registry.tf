# The images a cluster runs: Pinecall's own (the runtime, its Postgres), built by CodeBuild from
# infra/images and pulled by the nodes' own role. Elastic Container Registry holds a repository an
# image, so the registry an image's name begins with is <account>.dkr.ecr.<region>.amazonaws.com/pinecall.

resource "aws_ecr_repository" "images" {
  for_each = toset(var.images)
  name     = "pinecall/${each.value}"
  # A tag is a commit and may be pushed again; a release names the digest, which cannot be.
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

# A build that was replaced leaves its layers untagged: gone after two weeks. A tagged image is a
# release somebody may go back to and is never expired here.
resource "aws_ecr_lifecycle_policy" "images" {
  for_each   = aws_ecr_repository.images
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "untagged images, two weeks after they were pushed"
      selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 14 }
      action       = { type = "expire" }
    }]
  })
}

# api e voice-agent usam a mesma imagem (mesmo Dockerfile em ./backend no
# docker-compose), só mudam o comando do container — um repo ECR só.
resource "aws_ecr_repository" "rumolog_backend" {
  name                 = "rumolog-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "rumolog_backend" {
  repository = aws_ecr_repository.rumolog_backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expira imagens sem tag depois de 14 dias"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 14
      }
      action = {
        type = "expire"
      }
    }]
  })
}

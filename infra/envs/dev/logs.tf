resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/rumolog-dev/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "voice_agent" {
  name              = "/ecs/rumolog-dev/voice-agent"
  retention_in_days = var.log_retention_days
}

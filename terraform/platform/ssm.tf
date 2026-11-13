# Created with a placeholder; the real values are set in the console
# (Systems Manager > Parameter Store) so they never pass through a terminal.
resource "aws_ssm_parameter" "github_key" {
  name        = "/${var.project}/github-app-private-key"
  description = "GitHub App private key (PEM)"
  type        = "SecureString"
  tier        = "Advanced" # PEM keys are larger than the 4 KB standard limit
  value       = "set-me-in-the-console"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "webhook_secret" {
  name        = "/${var.project}/github-webhook-secret"
  description = "GitHub App webhook secret"
  type        = "SecureString"
  value       = "set-me-in-the-console"

  lifecycle {
    ignore_changes = [value]
  }
}

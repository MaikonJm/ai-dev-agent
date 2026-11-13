variable "project" {
  type    = string
  default = "ai-dev-agent"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket" {
  description = "Terraform state bucket of aws-sre-ai-platform/bootstrap (foundation state is read from it)"
  type        = string
}

variable "image_tag" {
  description = "Tag of the runner image in ECR (7-char commit SHA pushed by the Image workflow)"
  type        = string
}

variable "github_repo" {
  description = "Repository the agent works on"
  type        = string
  default     = "MaikonJm/agent-sandbox-shop"
}

variable "github_app_id" {
  type = string
}

variable "github_installation_id" {
  type = string
}

variable "allowed_users" {
  description = "GitHub logins allowed to trigger the agent (comma-separated)"
  type        = string
  default     = "MaikonJm"
}

variable "plan_model_id" {
  type    = string
  default = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "impl_model_id" {
  type    = string
  default = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "budget" {
  description = "Per-task limits"
  type = object({
    max_iterations = number
    max_tokens     = number
    max_seconds    = number
    max_cost_usd   = number
  })
  default = { max_iterations = 40, max_tokens = 400000, max_seconds = 1200, max_cost_usd = 0.75 }
}

variable "alarm_email" {
  description = "E-mail for alarms (confirm the SNS subscription)"
  type        = string
}

variable "daily_cost_alarm_usd" {
  description = "Alarm when the agent's model spend in one day passes this value"
  type        = number
  default     = 2
}

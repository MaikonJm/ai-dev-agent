variable "project" {
  description = "Prefix for every resource"
  type        = string
  default     = "ai-dev-agent"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block of the sandbox VPC"
  type        = string
  default     = "10.30.0.0/16"
}

variable "state_bucket" {
  description = "Terraform state bucket created by the aws-sre-ai-platform bootstrap stack"
  type        = string
}

variable "github_oidc_subject_prefix" {
  description = "OIDC sub prefix allowed to assume the CI role (GitHub's immutable owner@ID/repo@ID format)"
  type        = string
  default     = "repo:MaikonJm@37089888/ai-dev-agent@1455999706"
}

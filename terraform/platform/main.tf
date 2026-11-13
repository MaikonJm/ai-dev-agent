data "aws_caller_identity" "current" {}

data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "ai-dev-agent/foundation.tfstate"
    region = var.region
  }
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  foundation = data.terraform_remote_state.foundation.outputs
  container  = "agent"
}

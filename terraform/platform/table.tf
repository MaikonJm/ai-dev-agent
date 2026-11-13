resource "aws_dynamodb_table" "tasks" {
  name         = "${var.project}-tasks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "issue"

  attribute {
    name = "issue"
    type = "N"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }
}

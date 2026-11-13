output "webhook_url" {
  description = "Paste into the GitHub App's webhook URL"
  value       = "${aws_apigatewayv2_api.this.api_endpoint}/github/webhook"
}

output "table_name" {
  value = aws_dynamodb_table.tasks.name
}

output "queue_url" {
  value = aws_sqs_queue.jobs.url
}

output "dashboard_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${var.project}"
}

output "parameters_to_set" {
  description = "Set these values in the console (Systems Manager > Parameter Store)"
  value       = [aws_ssm_parameter.github_key.name, aws_ssm_parameter.webhook_secret.name]
}

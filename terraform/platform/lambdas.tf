# Each Lambda zip holds the agent package plus its own handler.
locals {
  agent_files = fileset("${path.module}/../../agent", "*.py")
}

data "archive_file" "lambda" {
  for_each    = toset(["webhook", "dispatcher"])
  type        = "zip"
  output_path = "${path.module}/build/${each.key}.zip"

  dynamic "source" {
    for_each = local.agent_files
    content {
      content  = file("${path.module}/../../agent/${source.value}")
      filename = "agent/${source.value}"
    }
  }

  source {
    content  = ""
    filename = "lambdas/__init__.py"
  }

  source {
    content  = ""
    filename = "lambdas/${each.key}/__init__.py"
  }

  source {
    content  = file("${path.module}/../../lambdas/${each.key}/app.py")
    filename = "lambdas/${each.key}/app.py"
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = toset(["webhook", "dispatcher"])
  name              = "/aws/lambda/${var.project}-${each.key}"
  retention_in_days = 14
}

resource "aws_lambda_function" "webhook" {
  function_name    = "${var.project}-webhook"
  role             = aws_iam_role.webhook.arn
  runtime          = "python3.12"
  handler          = "lambdas.webhook.app.handler"
  filename         = data.archive_file.lambda["webhook"].output_path
  source_code_hash = data.archive_file.lambda["webhook"].output_base64sha256
  timeout          = 10
  memory_size      = 256

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      TABLE_NAME           = aws_dynamodb_table.tasks.name
      QUEUE_URL            = aws_sqs_queue.jobs.url
      ALLOWED_USERS        = var.allowed_users
      WEBHOOK_SECRET_PARAM = aws_ssm_parameter.webhook_secret.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "dispatcher" {
  function_name    = "${var.project}-dispatcher"
  role             = aws_iam_role.dispatcher.arn
  runtime          = "python3.12"
  handler          = "lambdas.dispatcher.app.handler"
  filename         = data.archive_file.lambda["dispatcher"].output_path
  source_code_hash = data.archive_file.lambda["dispatcher"].output_base64sha256
  timeout          = 30
  memory_size      = 256

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      CLUSTER         = aws_ecs_cluster.this.name
      TASK_DEFINITION = aws_ecs_task_definition.runner.arn
      SUBNETS         = join(",", local.foundation.subnet_ids)
      SECURITY_GROUP  = local.foundation.sandbox_security_group_id
      CONTAINER_NAME  = local.container
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_event_source_mapping" "jobs" {
  event_source_arn        = aws_sqs_queue.jobs.arn
  function_name           = aws_lambda_function.dispatcher.arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
}

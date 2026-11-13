data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- webhook Lambda: read the secret, write task state, enqueue jobs
resource "aws_iam_role" "webhook" {
  name               = "${var.project}-webhook"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "webhook" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.webhook_secret.arn]
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.tasks.arn]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.jobs.arn]
  }
}

resource "aws_iam_role_policy" "webhook" {
  role   = aws_iam_role.webhook.id
  policy = data.aws_iam_policy_document.webhook.json
}

# --- dispatcher Lambda: consume jobs, start Fargate tasks
resource "aws_iam_role" "dispatcher" {
  name               = "${var.project}-dispatcher"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "dispatcher" {
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.jobs.arn]
  }
  statement {
    actions   = ["ecs:RunTask"]
    resources = ["arn:aws:ecs:${var.region}:${local.account_id}:task-definition/${aws_ecs_task_definition.runner.family}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.task.arn, aws_iam_role.task_execution.arn]
  }
}

resource "aws_iam_role_policy" "dispatcher" {
  role   = aws_iam_role.dispatcher.id
  policy = data.aws_iam_policy_document.dispatcher.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each   = { webhook = aws_iam_role.webhook.name, dispatcher = aws_iam_role.dispatcher.name }
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_xray" {
  for_each   = { webhook = aws_iam_role.webhook.name, dispatcher = aws_iam_role.dispatcher.name }
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# --- Fargate execution role: pull the image, write logs
resource "aws_iam_role" "task_execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- the agent itself: invoke two models, its own task item, the App key. Nothing else.
resource "aws_iam_role" "task" {
  name               = "${var.project}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid     = "InvokeConfiguredModels"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    # Cross-region inference profiles route to the foundation model in several US regions
    resources = flatten([for id in [var.plan_model_id, var.impl_model_id] : [
      "arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/${id}",
      "arn:aws:bedrock:*::foundation-model/${trimprefix(id, "us.")}",
    ]])
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.tasks.arn]
  }
  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.github_key.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

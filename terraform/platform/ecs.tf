resource "aws_ecs_cluster" "this" {
  name = var.project
}

resource "aws_cloudwatch_log_group" "runner" {
  name              = "/ecs/${var.project}-runner"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "runner" {
  family                   = "${var.project}-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = local.container
    image     = "${local.foundation.ecr_repository_url}:${var.image_tag}"
    essential = true
    environment = [
      { name = "AWS_REGION", value = var.region },
      { name = "TABLE_NAME", value = aws_dynamodb_table.tasks.name },
      { name = "PLAN_MODEL_ID", value = var.plan_model_id },
      { name = "IMPL_MODEL_ID", value = var.impl_model_id },
      { name = "GITHUB_APP_ID", value = var.github_app_id },
      { name = "GITHUB_INSTALLATION_ID", value = var.github_installation_id },
      { name = "GITHUB_REPO", value = var.github_repo },
      { name = "GITHUB_KEY_PARAM", value = aws_ssm_parameter.github_key.name },
      { name = "MAX_ITERATIONS", value = tostring(var.budget.max_iterations) },
      { name = "MAX_TOKENS", value = tostring(var.budget.max_tokens) },
      { name = "MAX_SECONDS", value = tostring(var.budget.max_seconds) },
      { name = "MAX_COST_USD", value = tostring(var.budget.max_cost_usd) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.runner.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "runner"
      }
    }
  }])
}

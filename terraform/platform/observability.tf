resource "aws_sns_topic" "alarms" {
  name = "${var.project}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${var.project}-jobs-dlq-not-empty"
  alarm_description   = "Jobs failed to start a Fargate task 3 times"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "failed_tasks" {
  alarm_name          = "${var.project}-failed-tasks"
  alarm_description   = "The agent ended a task as FAILED"
  namespace           = "AIDevAgent"
  metric_name         = "TasksCompleted"
  dimensions          = { Outcome = "FAILED" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# Alarms cannot use SEARCH expressions, so the cost metric is read once per
# outcome the runner emits (agent/runner.py) and the series are added up.
locals {
  outcomes = ["AWAITING_APPROVAL", "PR_OPENED", "FAILED", "BUDGET_EXCEEDED"]
}

resource "aws_cloudwatch_metric_alarm" "daily_cost" {
  alarm_name          = "${var.project}-daily-model-cost"
  alarm_description   = "Model spend in the last day passed the limit"
  evaluation_periods  = 1
  threshold           = var.daily_cost_alarm_usd
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]

  dynamic "metric_query" {
    for_each = local.outcomes
    content {
      id          = "m${metric_query.key}"
      return_data = false

      metric {
        namespace   = "AIDevAgent"
        metric_name = "CostUSD"
        dimensions  = { Outcome = metric_query.value }
        stat        = "Sum"
        period      = 86400
      }
    }
  }

  metric_query {
    id          = "cost"
    label       = "Model cost in the last day (USD)"
    expression  = join(" + ", [for i in range(length(local.outcomes)) : "FILL(m${i}, 0)"])
    return_data = true
  }
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.project
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title   = "Tasks by outcome", region = var.region, stat = "Sum", period = 3600, view = "timeSeries",
          metrics = [[{ expression = "SEARCH('{AIDevAgent,Outcome} MetricName=\"TasksCompleted\"', 'Sum', 3600)", id = "t" }]]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title   = "Model cost (USD)", region = var.region, stat = "Sum", period = 3600, view = "timeSeries",
          metrics = [[{ expression = "SEARCH('{AIDevAgent,Outcome} MetricName=\"CostUSD\"', 'Sum', 3600)", id = "c" }]]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title   = "Tokens", region = var.region, stat = "Sum", period = 3600, view = "timeSeries",
          metrics = [[{ expression = "SEARCH('{AIDevAgent,Outcome} MetricName=(\"TokensIn\" OR \"TokensOut\")', 'Sum', 3600)", id = "k" }]]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title   = "Task duration (s)", region = var.region, stat = "Average", period = 3600, view = "timeSeries",
          metrics = [[{ expression = "SEARCH('{AIDevAgent,Outcome} MetricName=\"DurationSeconds\"', 'Average', 3600)", id = "d" }]]
        }
      },
    ]
  })
}

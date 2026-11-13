output "ecr_repository_url" {
  value = aws_ecr_repository.runner.repository_url
}

output "subnet_ids" {
  value = aws_subnet.public[*].id
}

output "sandbox_security_group_id" {
  value = aws_security_group.sandbox.id
}

output "ci_role_arn" {
  value = aws_iam_role.github_ci.arn
}

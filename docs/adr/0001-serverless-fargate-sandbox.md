# ADR 0001: Serverless pipeline with a Fargate sandbox

- **Status:** accepted
- **Date:** 2026-11-12

## Context

The agent must run untrusted work (model-written code and its tests) in isolation, cost nothing while idle and fit a small AWS budget shared with other projects.

## Options

1. **API Gateway → Lambda → SQS → ECS Fargate task per job.** Event-driven, no idle cost, strong isolation (one task per job, no inbound, HTTPS egress only).
2. **GitHub Actions runner as the sandbox.** Simplest and cheapest, but almost nothing runs on AWS and the agent reads as a CI script.
3. **Kubernetes jobs on k3s.** Repeats the previous project and the EC2 node costs while it is up.

## Decision

Option 1. The webhook Lambda only verifies and records; the dispatcher Lambda only starts tasks; all agent work runs in a short-lived Fargate task with a role limited to two Bedrock models, its DynamoDB item and the GitHub App key.

## Consequences

- Idle cost is close to zero; each job pays for a few minutes of Fargate (0.5 vCPU, 1 GB) plus model tokens.
- More moving parts than option 2, covered by per-component tests and a CloudWatch dashboard.
- Fargate tasks need a public IP to reach GitHub and Bedrock without a NAT gateway; the security group allows no inbound traffic.

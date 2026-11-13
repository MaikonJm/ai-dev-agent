# AI Dev Agent: design

- **Date:** 2026-11-12
- **Owner:** Maikon Marquez
- **Status:** approved (2026-11-12); model: Claude on Bedrock

## Intent

A second senior-level portfolio project, focused on AI agents, that also feeds LinkedIn content and fits the AI Agents post-graduate course.

The agent does development work the way a teammate would. It picks up a GitHub issue, proposes a plan, writes the code and tests in an isolated sandbox, runs them, and opens a pull request with a report. A human approves the plan and merges the PR. The story it tells: an autonomous agent that is safe to run because of the engineering around it (isolation, least privilege, budgets, observability, evaluation), not because the model is perfect.

## Goals

- Issue labeled `agent` → plan comment → `/approve` → pull request with code, tests and a report (what changed, how it was tested, tokens and cost, open questions).
- `/revise <feedback>` on the plan or the PR makes the agent try again with the feedback.
- Runs on AWS, serverless and event-driven: no idle cost.
- Measurable: a small evaluation suite of known issues reports success rate, cost and duration per agent version.
- Documented like project 1: README with architecture, ADRs, runbook, test sessions and blameless post-mortems.

## Non-goals

- Creating whole applications from a description (possible later evolution).
- Working on more than one target repository, or on languages other than Python.
- A web dashboard (GitHub issues and PRs are the interface).
- Changing the `aws-sre-ai-platform` repository. Integration with the SRE agent may come later, on a fork.

## Anti-goals (failure even if it "works")

- The agent pushes to `main`, merges its own PR, or acts without the plan being approved.
- A secret or AWS account ID ends up in a comment, PR or log.
- A runaway task spends money without limit.

## Repositories

- `MaikonJm/ai-dev-agent` (public): agent code, infrastructure, docs.
- `MaikonJm/agent-sandbox-shop` (public): a small Python FastAPI shop (products, cart, orders) with pytest and CI. It ships with planted work for the agent: a real bug, missing tests and a small feature request. The agent only ever opens PRs here.

## Approaches considered

1. **Serverless on AWS (chosen).** GitHub webhook → API Gateway → Lambda → SQS → ECS Fargate task as the sandbox; Bedrock for the model; DynamoDB for task state. Zero cost when idle, showcases event-driven serverless design (different from project 1's Kubernetes), more moving parts.
2. **Inside GitHub Actions.** The runner is the sandbox. Simplest and cheapest, but almost no AWS to show and reads as a CI script.
3. **Kubernetes jobs on k3s.** Repeats project 1 and the EC2 node costs while it is up.

Maikon picked option 1.

## Architecture

```
GitHub (agent-sandbox-shop)
  │  issue labeled "agent" / comment "/approve" or "/revise ..."
  ▼
API Gateway (HTTP API)  ──►  Lambda "webhook"
                               - verifies the GitHub HMAC signature
                               - ignores everything but the events above, from allowed users
                               - writes/updates the task in DynamoDB, sends a job to SQS
                                        │
                                        ▼
                              SQS jobs queue (+ DLQ, alarm)
                                        │
                                        ▼
                               Lambda "dispatcher" ──► ECS RunTask (Fargate)
                                                          │
                                                          ▼
                                    Sandbox container (the agent)
                                    - GitHub App installation token (short-lived)
                                    - clone repo, run the agent loop on Bedrock
                                    - phase "plan": comment the plan, stop
                                    - phase "implement": edit, run tests, push branch, open PR
                                    - write metrics and the final record
```

### Task lifecycle (DynamoDB)

`RECEIVED → PLANNING → AWAITING_APPROVAL → IMPLEMENTING → PR_OPENED → DONE`, plus `FAILED` and `BUDGET_EXCEEDED`. `/revise` moves back to `PLANNING` or `IMPLEMENTING` with the feedback attached. One record per issue, with attempts, tokens, cost, duration and links.

### The agent loop

A small agent written for this project on the Bedrock Converse API with tool use, not a framework, so every step is visible and testable. Tools:

- `list_files`, `read_file`, `search_code`
- `write_file` (only inside the cloned repo, size-limited)
- `run_command` (allowlist: `pytest`, `ruff`, `pip install -r requirements*.txt`, `git diff`, `git status`)
- `finish` with a structured summary

The orchestration code, not the model, does git branch/commit/push, PR creation and comments.

### Model

Configurable Bedrock model ID. Default: a Claude Sonnet model on Bedrock for implementation and a cheaper model (Claude Haiku or Amazon Nova) for planning; both need Bedrock model access enabled in the account. Builder may adjust after the first evaluation run.

## Guardrails

- **Approval gate:** no code is written before `/approve` from an allowed GitHub user.
- **GitHub App, least privilege:** installed only on `agent-sandbox-shop`; permissions limited to contents, issues and pull requests; tokens expire in 1 hour; branch protection on `main` (PR + passing CI required).
- **Sandbox:** one Fargate task per job, no AWS permissions except Bedrock invoke on the configured models, writing its own logs/metrics and its DynamoDB item; egress only HTTPS; no inbound.
- **Budgets per task:** max iterations, max tokens, max wall-clock time, max cost; exceeding any stops the task as `BUDGET_EXCEEDED` with a comment.
- **Untrusted input:** issue text, comments and repository content are data, never instructions to change the agent's rules; the system prompt says so and tools enforce limits regardless.
- **Output checks:** secrets and 12-digit account IDs are redacted from every comment and PR body; diffs over a size limit are refused.
- **Webhook:** HMAC signature verification, replay protection by delivery ID, allowlist of GitHub users who can trigger the agent.

## Observability

- Structured JSON logs in CloudWatch, one correlation ID per task.
- Custom metrics: tasks by outcome, tokens in/out, cost per task, duration, tool calls, test pass rate.
- CloudWatch dashboard and alarms: DLQ not empty, failed tasks, monthly agent cost.
- X-Ray tracing on the Lambdas.

## Evaluation

An `evals/` suite of known issues against `agent-sandbox-shop`, each with a hidden acceptance test. A script runs them through the real pipeline and reports success rate, cost and duration per agent version. Results are committed so improvements are measurable over time.

## Infrastructure and delivery

- Terraform, reusing project 1's bootstrap (state bucket, budgets) with new state keys; stacks: `foundation` (ECR, OIDC role for this repo, networking for Fargate without NAT), `platform` (API Gateway, Lambdas, SQS, DynamoDB, ECS cluster and task definition, alarms, dashboard).
- Fargate runs in public subnets with a public IP and an egress-only-HTTPS security group, so no NAT gateway is needed.
- GitHub Actions: ruff and pytest, Terraform fmt/validate/plan, image build and push to ECR via OIDC.
- Secrets: GitHub App private key and webhook secret in SSM Parameter Store (SecureString).

## Constraints

- Free-tier-friendly; AWS credits are shared with the post-graduate course. Idle cost should be near zero; per-task cost targeted under US$0.50.
- The person running sessions works through CloudShell and the browser; setup steps must avoid pasting secrets into terminals.
- Public repositories: nothing sensitive in code, issues, PRs or screenshots.

## Left to the builder

- Exact Bedrock model IDs and token prices after checking availability in us-east-1.
- Fargate CPU/memory sizing; budget limit values.
- Webhook delivery via GitHub App webhook (preferred) or repository webhook.
- Content of the planted issues in the sandbox repository.
- Python libraries (boto3, httpx, PyGithub or plain REST).

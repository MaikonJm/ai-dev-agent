# AI Dev Agent

> An autonomous development agent on AWS. Label a GitHub issue, approve the plan it proposes, and it writes the code and the tests in an isolated Fargate sandbox and opens a pull request with a report. It never merges: a human always decides.

![Status](https://img.shields.io/badge/status-built%2C%20AWS%20test%20pending-yellow)
![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-232F3E?logo=amazonwebservices&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![CI](https://github.com/MaikonJm/ai-dev-agent/actions/workflows/ci.yml/badge.svg)

![Architecture: GitHub issue webhook to API Gateway, webhook Lambda, SQS, dispatcher Lambda and a Fargate task running the agent, which calls Amazon Bedrock and opens a pull request; DynamoDB state, Parameter Store secrets, CloudWatch, SNS and X-Ray](docs/images/architecture.png)

## How it works

1. You add the label `agent` to an issue in [agent-sandbox-shop](https://github.com/MaikonJm/agent-sandbox-shop).
2. GitHub calls the webhook. The **webhook Lambda** checks the signature, the sender and duplicates, records the task in DynamoDB and queues a job.
3. The **dispatcher Lambda** starts one **Fargate task**. The agent clones the repository, explores it with read-only tools and **comments a plan** on the issue.
4. You reply `/approve` (or `/revise <feedback>`).
5. A new task implements the plan, runs the tests and, only if they pass, **pushes `agent/issue-N` and opens a PR** with what changed, how it was tested, open questions, tokens and cost.
6. You review and merge.

## Guardrails

| Risk | Control |
| --- | --- |
| The agent changes things without approval | Plan phase has read-only tools; code is written only after `/approve` from an allowed user |
| It merges or breaks `main` | Pushes only `agent/issue-N`; `main` refused in code and protected by branch protection |
| Escaping the workspace | Every path must resolve inside the clone (no `..`, absolute paths or symlinks out) |
| Running arbitrary commands | Allowlist (`pytest`, `ruff`, `pip install -r requirements*.txt`, `git diff/status`), no shell, 300 s timeout |
| Prompt injection from issues or code | Issue, plan and feedback are fenced as untrusted data; limits are enforced by code, not by the prompt |
| Runaway cost | Per-task limits on steps, tokens, time and dollars; daily spend alarm |
| Secrets leaking | GitHub App tokens live 1 hour; keys in Parameter Store; every comment and PR is redacted (keys, tokens, account IDs) |
| Broad cloud access | The agent's role can invoke two models, update its own table and read one parameter. Nothing else. |
| Duplicated work | Webhook deliveries are deduplicated; state transitions are conditional; a job in the wrong state does nothing |

## Evaluation

[`evals/`](evals/) runs five known tasks (bug fix, tests, feature, validation, refactor) through the real pipeline and scores each PR with an acceptance test the agent never saw. Success rate, cost and duration are committed per run, so every change to prompts or models is measured the same way.

## Cost

Nothing runs while idle: API Gateway, Lambda, SQS and DynamoDB are pay-per-request, and Fargate tasks exist only while a job runs. A task costs a few minutes of Fargate (0.5 vCPU, 1 GB) plus model tokens, capped at US$0.75 by default.

## Repository structure

```text
agent/          # the agent: settings, budget, redaction, tools, LLM client, loop, GitHub App, store, runner
lambdas/        # webhook and dispatcher handlers
evals/          # known tasks, hidden acceptance tests, results
terraform/
  foundation/   # VPC without NAT, sandbox security group, ECR, CI role (OIDC)
  platform/     # API Gateway, Lambdas, SQS + DLQ, DynamoDB, ECS/Fargate, IAM, SSM, alarms, dashboard
docs/           # ADRs, runbook, design, plan, post-mortems, diagram source
```

## Getting started

Step by step, including the GitHub App and Bedrock model access: [docs/runbook.md](docs/runbook.md).

```bash
pip install -e ".[dev]"
pytest -q          # 78 tests, no AWS needed
```

## Design decisions

| Decision | Why |
| --- | --- |
| Serverless + Fargate sandbox | Zero idle cost and one isolated task per job ([ADR 0001](docs/adr/0001-serverless-fargate-sandbox.md)) |
| Own agent loop on Bedrock Converse | Every step visible and testable ([ADR 0002](docs/adr/0002-own-agent-loop.md)) |
| GitHub App | Short-lived, single-repository credentials ([ADR 0003](docs/adr/0003-github-app-auth.md)) |
| Two models | A cheaper model plans, a stronger one implements |
| Hidden acceptance tests | The agent cannot game the evaluation |

## Roadmap

- [x] Design, plan and implementation with tests (78)
- [x] Terraform for both stacks, validated in CI
- [ ] First test session on AWS and evaluation results
- [ ] Post-mortem and write-up

---

**Maikon Marquez** · Cloud & DevOps Engineer · [LinkedIn](https://www.linkedin.com/in/maikon-marquez) · [GitHub](https://github.com/MaikonJm) · [Medium](https://medium.com/@maikonjm)

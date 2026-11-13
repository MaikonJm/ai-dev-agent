# Runbook: first deployment and test session

Everything below happens in the browser and in AWS CloudShell. No secret is ever pasted into a terminal.

## 0. Prerequisites

- The `aws-sre-ai-platform` bootstrap stack exists (state bucket and AWS Budgets).
- Its foundation stack exists too: it owns the GitHub OIDC provider this project reuses.

## 1. Enable the models in Bedrock

Console → Amazon Bedrock → Model access → enable **Claude Haiku 4.5** and **Claude Sonnet 4.5** (Anthropic asks for a short use-case form). Check the exact model IDs under *Cross-region inference* and update `plan_model_id` / `impl_model_id` if they differ from the defaults.

## 2. Foundation stack

```bash
cd ~/ai-dev-agent/terraform/foundation
cp backend.hcl.example backend.hcl          # set ACCOUNT_ID
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl && terraform apply
```

Then set the repository variable `AWS_ACCOUNT_ID` (GitHub → Settings → Secrets and variables → Actions → Variables) and re-run the **Image** workflow on `main`: it pushes the runner image to ECR. Note the 7-character tag.

## 3. Create the GitHub App

GitHub → Settings → Developer settings → GitHub Apps → New GitHub App:

- **Name:** `ai-dev-agent-<your-login>`, homepage: the repository URL.
- **Webhook:** active; URL filled in step 5; **secret:** generate a random string and keep the tab open.
- **Repository permissions:** Contents *Read and write*, Issues *Read and write*, Pull requests *Read and write*, Metadata *Read*.
- **Subscribe to events:** Issues, Issue comment.
- **Where can it be installed:** Only on this account.

After creating: note the **App ID**, generate a **private key** (downloads a `.pem`), then **Install App** → only `agent-sandbox-shop`. The installation ID is the number at the end of the installation page URL.

## 4. Platform stack

```bash
cd ~/ai-dev-agent/terraform/platform
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars   # image_tag, app ID, installation ID, alarm e-mail
terraform init -backend-config=backend.hcl && terraform apply
```

Confirm the SNS subscription e-mail.

## 5. Secrets and webhook

- Console → Systems Manager → Parameter Store → `/ai-dev-agent/github-app-private-key` → Edit → paste the whole `.pem` content → Save.
- Same for `/ai-dev-agent/github-webhook-secret` with the webhook secret from step 3.
- GitHub App settings → Webhook URL = the `webhook_url` output → Save.

## 6. Branch protection on the sandbox

`agent-sandbox-shop` → Settings → Branches → add a rule for `main`: require a pull request and the `CI` status check.

## 7. First run

1. Create the `agent` label in `agent-sandbox-shop`.
2. Add it to issue #1. Within about a minute the app comments a plan.
3. Reply `/approve`. A few minutes later a PR appears with the fix, the tests and a usage line.
4. Review and merge (or `/revise <feedback>`).

Watch: CloudWatch dashboard `ai-dev-agent`, log groups `/aws/lambda/ai-dev-agent-*` and `/ecs/ai-dev-agent-runner`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No reaction to the label | GitHub App → Advanced → Recent deliveries: status 401 = webhook secret mismatch; 204 = sender not in `allowed_users` or wrong label |
| Plan never arrives | Dispatcher logs (RunTask errors), DLQ alarm, runner logs |
| `AccessDeniedException` from Bedrock | Model access not enabled, or model ID differs from the IAM policy |
| Runner fails cloning | App not installed on the repository, or wrong installation ID |
| `BUDGET_EXCEEDED` comment | Narrow the issue, or raise `budget` in `terraform.tfvars` |

## Tear down

Platform first, then foundation: `terraform destroy` in each. Nothing in this project has an hourly cost while idle, so destroying is optional between sessions.

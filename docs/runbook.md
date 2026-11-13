# Runbook: first deployment and test session

Everything below happens in the browser and in AWS CloudShell (us-east-1). No secret is ever pasted into a terminal, and the AWS account ID never leaves the account: it is only written to git-ignored files inside CloudShell.

Paste one command at a time. A pasted block that contains an interactive prompt swallows the lines that follow it.

## 0. Prerequisites

- The `aws-sre-ai-platform` bootstrap stack exists (state bucket and AWS Budgets). Check it, and re-apply `terraform/bootstrap` of that project if the bucket is gone:

  ```bash
  aws s3api head-bucket --bucket "aws-sre-ai-platform-tfstate-$(aws sts get-caller-identity --query Account --output text)" >/dev/null && echo "state bucket: ok"
  ```

- The GitHub OIDC provider exists in the account (the foundation stack only reads it):

  ```bash
  aws iam list-open-id-connect-providers --output text | grep -c token.actions.githubusercontent.com
  ```

- Terraform 1.10 or newer and Docker are available in CloudShell. Terraform is not preinstalled; unzip the release into `~/.local/bin`, which survives between sessions. If an old `~/.terraformrc` points to a plugin cache under `/tmp`, recreate the directory (`mkdir -p /tmp/tf-plugin-cache`).

## 1. Model access in Bedrock

Anthropic asks first-time customers for use-case details once per account. Bedrock lets the first few calls through and then answers `Model use case details have not been submitted for this account`, so do this before anything else:

Console → Amazon Bedrock → Model catalog → **Submit use case details** (yellow banner). Approval takes up to 15 minutes.

Then test both models the way the agent calls them. Both must answer `max_tokens`:

```bash
aws bedrock-runtime converse --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 --messages '[{"role":"user","content":[{"text":"ping"}]}]' --inference-config maxTokens=5,temperature=0.2 --query stopReason --output text
```

```bash
aws bedrock-runtime converse --model-id us.anthropic.claude-sonnet-4-6 --messages '[{"role":"user","content":[{"text":"ping"}]}]' --inference-config maxTokens=5,temperature=0.2 --query stopReason --output text
```

A model marked *Legacy* is refused for accounts that have not used it in the last 30 days. List the current inference profiles with `aws bedrock list-inference-profiles` and set `plan_model_id` / `impl_model_id` in `terraform.tfvars` if the defaults stop working. A model of a new family also needs a price in `agent.llm.PRICES`.

## 2. Foundation stack and runner image

```bash
cd ~/ai-dev-agent/terraform/foundation
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed "s/ACCOUNT_ID/$ACCOUNT_ID/" backend.hcl.example > backend.hcl
sed "s/ACCOUNT_ID/$ACCOUNT_ID/" terraform.tfvars.example > terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -out=/tmp/foundation.tfplan      # 16 to add
terraform apply /tmp/foundation.tfplan
```

Build and push the runner image from CloudShell. The tag is the 7-character commit SHA:

```bash
cd ~/ai-dev-agent
TAG=$(git rev-parse --short=7 HEAD)
REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
docker build -t "$REGISTRY/ai-dev-agent/runner:$TAG" .
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker push "$REGISTRY/ai-dev-agent/runner:$TAG"
```

The **Image** workflow can push instead if the repository variable `AWS_ACCOUNT_ID` is set, but Actions variables are not masked: on a public repository the account ID then shows up in the workflow logs. Prefer the CloudShell push unless that is acceptable.

Rebuild and push again, with the new tag, whenever `agent/`, `Dockerfile` or `pyproject.toml` change; then update `image_tag` and apply the platform stack.

## 3. Create the GitHub App

GitHub → Settings → Developer settings → GitHub Apps → New GitHub App:

- **Name:** `ai-dev-agent-<your-login>`, homepage: the repository URL.
- **Webhook:** leave **Active** unchecked for now; the URL only exists after step 4.
- **Repository permissions:** Contents *Read and write*, Issues *Read and write*, Pull requests *Read and write*, Metadata *Read*.
- **Where can it be installed:** Only on this account.

After creating:

- note the **App ID** (General);
- **Credentials → Key pairs → New key** downloads the private key (`.pem`). Do not create a client secret;
- **Install App** → Only select repositories → `agent-sandbox-shop`. The installation ID is the number at the end of the installation page URL.

## 4. Platform stack

```bash
cd ~/ai-dev-agent/terraform/platform
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed "s/ACCOUNT_ID/$ACCOUNT_ID/" backend.hcl.example > backend.hcl
sed "s/ACCOUNT_ID/$ACCOUNT_ID/" terraform.tfvars.example > terraform.tfvars
nano terraform.tfvars                          # image_tag, app ID, installation ID, alarm e-mail
terraform init -backend-config=backend.hcl
terraform plan -out=/tmp/platform.tfplan       # 36 to add
terraform apply /tmp/platform.tfplan
terraform output -raw webhook_url
```

Confirm the SNS subscription e-mail.

## 5. Secrets and webhook

Set both parameters **before** activating the webhook. The webhook Lambda reads its secret once per warm instance, so a delivery that arrives earlier keeps the placeholder in memory.

- Console → Systems Manager → Parameter Store → `/ai-dev-agent/github-app-private-key` → Edit → paste the whole `.pem` content → Save.
- Generate a long random string (a password manager works) and save it in `/ai-dev-agent/github-webhook-secret`.
- Check that both parameters are at version 2 (the command never shows the values):

  ```bash
  aws ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=/ai-dev-agent/" --query 'Parameters[].[Name,Version]' --output text
  ```

- GitHub App → General → Webhook: check **Active**, URL = the `webhook_url` output, Secret = the same string → Save changes.
- GitHub App → Permissions & events → Subscribe to events: **Issues** and **Issue comment** → Save changes.

## 6. Branch protection on the sandbox

`agent-sandbox-shop` → Settings → Branches → Add classic branch protection rule for `main`: require a pull request and the `test` status check (the job name of the sandbox CI workflow).

## 7. First run

1. Create the `agent` label in `agent-sandbox-shop`.
2. Add it to issue #1. Within about a minute the app comments a plan.
3. Reply `/approve` in the issue. A few minutes later a PR appears with the fix, the tests and a usage line.
4. Review and merge (or `/revise <feedback>`).

Follow the task state from CloudShell:

```bash
aws dynamodb get-item --table-name ai-dev-agent-tasks --key '{"issue":{"N":"1"}}' --query 'Item.state.S' --output text
```

Watch: CloudWatch dashboard `ai-dev-agent`, log groups `/aws/lambda/ai-dev-agent-*` and `/ecs/ai-dev-agent-runner`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No reaction to the label, state is `None` | GitHub App → Advanced → Recent deliveries: status 401 = webhook secret mismatch (parameter still at version 1, or the Lambda cached the old value); 204 = sender not in `allowed_users` or wrong label; no delivery = webhook inactive or events not subscribed |
| Secret fixed but still 401 | Force a new Lambda instance: `aws lambda update-function-configuration --function-name ai-dev-agent-webhook --description "reload secret"` (the next apply reverts the description) |
| Plan never arrives | Dispatcher logs (RunTask errors), DLQ alarm, runner logs |
| `Model use case details have not been submitted` | Step 1: submit the Anthropic form and wait up to 15 minutes |
| `This Model is marked by provider as Legacy` | Pick an active inference profile and set the model ID in `terraform.tfvars` |
| `AccessDeniedException` from Bedrock | Model ID differs from the IAM policy of the task role |
| Runner fails cloning | App not installed on the repository, or wrong installation ID |
| A failed plan phase needs a fresh start | Delete the task item (`aws dynamodb delete-item --table-name ai-dev-agent-tasks --key '{"issue":{"N":"1"}}'`), then remove and re-add the label. `/revise` after a failure goes to the implement phase |
| `BUDGET_EXCEEDED` comment | Narrow the issue, or raise `budget` in `terraform.tfvars` |

## Tear down

Platform first, then foundation, each from a saved destroy plan:

```bash
terraform plan -destroy -out=/tmp/destroy.tfplan
terraform apply /tmp/destroy.tfplan
```

Nothing in this project has an hourly cost while idle, so destroying is optional between sessions. For a complete clean-up, also:

- delete the inactive task definitions, which ECS keeps after a destroy: `aws ecs delete-task-definitions --task-definitions ai-dev-agent-runner:1` (one per revision);
- delete the GitHub App (Advanced → Delete GitHub App) and the downloaded `.pem`;
- remove the CloudShell clone, which holds `terraform.tfvars`;
- empty and delete the state bucket in the S3 console if `aws-sre-ai-platform` is not using it (it is versioned and protected by `prevent_destroy`).

The Resource Groups Tagging API may keep listing destroyed resources for a few minutes; confirm with the service's own `describe`/`list` call.

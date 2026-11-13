# Post-mortem: first deployment and test session

- **Date:** 2026-11-13
- **Status:** final
- **Severity:** ticket
- **Authors:** Maikon Marquez

> Blameless: this document is about how the system and the process allowed the failures, not about who did what.

## Summary

The first deployment on AWS followed [the runbook](../runbook.md) from an empty account state to a merged pull request and a full tear-down in about 1 h 40 min. The agent did what it was built for: it planned the fix for [issue #1](https://github.com/MaikonJm/agent-sandbox-shop/issues/1) of the sandbox, waited for `/approve`, and opened [PR #4](https://github.com/MaikonJm/agent-sandbox-shop/pull/4) with the correct change. On the way, the session hit six problems that the 78 unit tests and `terraform validate` could not see. Two were code defects fixed during the session, one is still open.

## Impact

- No user impact: test session on a sandbox repository.
- Two agent runs ended as `FAILED` before the successful one. Neither produced a pull request.
- One `terraform apply` stopped at 35 of 36 resources.
- Model spend stayed below the US$0.75 per-task cap: US$0.0147 for the plan and US$0.2133 for the successful implementation (61,559 input and 1,905 output tokens, 43 s, 15 steps). The failed implement run is not included in these figures.
- Everything created (52 resources in two stacks) was destroyed at the end.

## Timeline (UTC, approximate)

| Time | Event |
| --- | --- |
| 16:20 | Pre-check: the Terraform state bucket is missing; Bedrock refuses Claude Sonnet 4.5 as a Legacy model |
| 16:28 | State bucket re-created with the bootstrap stack of `aws-sre-ai-platform` |
| 16:32 | Foundation stack applied (16 resources) |
| 16:35 | Runner image `c452749` built and pushed from CloudShell |
| 16:47 | GitHub App created and installed on `agent-sandbox-shop` only |
| 17:02 | Platform apply stops at 35/36: CloudWatch rejects the daily cost alarm |
| 17:07 | Fix merged ([#14](https://github.com/MaikonJm/ai-dev-agent/pull/14)); platform stack complete (36 resources) |
| 17:16 | Label `agent` added to issue #1: no reaction, no task item |
| 17:21 | Webhook secret set, Lambda restarted, label re-added. Run 1 ends as `FAILED`: Anthropic use-case form not submitted. The failed-task alarm e-mail arrives |
| 17:27 | Use-case form submitted in the Bedrock model catalog |
| 17:32 | Run 2 (plan): plan commented on the issue in 9 s, 5 steps, US$0.0147 |
| 17:33 | `/approve` |
| 17:35 | Run 3 (implement) ends as `FAILED`: `ImportError` when starting pytest |
| 17:40 | Fix merged ([#15](https://github.com/MaikonJm/ai-dev-agent/pull/15)), image `84d2607` deployed, `/revise` |
| 17:42 | Run 4 (implement): PR #4 opened after 43 s and 15 steps, US$0.2133 |
| 17:46 | PR reviewed and merged by a human |
| 18:00 | Platform and foundation destroyed; leftovers checked |

## Findings

### 1. The default implementation model had become Legacy

Bedrock refuses a Legacy model for accounts that did not use it in the last 30 days. The default `impl_model_id` was Claude Sonnet 4.5. The session used `us.anthropic.claude-sonnet-4-6` through `terraform.tfvars`; no code change was needed because the price table matches by model family and the IAM policy is built from the variable.

### 2. CloudWatch rejected the daily cost alarm

`aws_cloudwatch_metric_alarm.daily_cost` used a `SEARCH` expression. Dashboards accept it, alarms do not, and the API answered `Period must not be null`. `terraform validate` cannot catch this because the rule lives in the AWS API. Fixed in [#14](https://github.com/MaikonJm/ai-dev-agent/pull/14): the alarm reads `CostUSD` once per outcome and adds the series up.

### 3. The label did nothing: webhook secret still a placeholder

The webhook secret parameter was still at version 1, so the Lambda could not validate the signature and nothing reached the task table. The Lambda also reads the secret once per warm instance, so fixing the parameter alone is not enough if a delivery has already arrived. The runbook now sets both parameters before activating the webhook and has a command to check the parameter versions.

### 4. Anthropic use-case form on Bedrock

The first test calls from CloudShell succeeded, then every call failed with `Model use case details have not been submitted for this account`. The agent reported the error on the issue and the failed-task alarm fired, both as designed. The form is now step 1 of the runbook.

### 5. The image's pytest launcher against the repository's pytest

The image installs an unpinned pytest (9.2.0 that day). The agent then installs the sandbox's `requirements-dev.txt` with `PIP_USER=1`, which puts `pytest==8.3.4` in the user site. Imports resolved to 8.3.4 while `PATH` still pointed at the image's launcher, whose entry point does not exist in 8.3.4. Fixed in [#15](https://github.com/MaikonJm/ai-dev-agent/pull/15): the user-site `bin` comes first on `PATH`, so the tools pinned by the target repository are the ones that run.

### 6. `/revise` after a failed plan skips the plan (open)

After run 1 failed in the plan phase, `/revise` would have moved the task straight to the implement phase without a plan or an approval step. The session avoided it by deleting the task item and re-adding the label. The workaround is in the runbook; the state machine still needs the fix.

## Detection

- Findings 2 and 5 were detected by the system itself: a failed apply, and an agent comment with the traceback plus the failed-task alarm.
- Finding 4 was reported by the agent on the issue within seconds.
- Finding 3 was silent: nothing on the issue, no alarm. It was found by reading the task table and the parameter versions.

## AI agent assessment

- The plan matched the issue's acceptance criteria and named the two files that needed to change.
- The pull request changed 2 files (+2 −7): the loop in `cart_total()` now multiplies every item by its quantity, and the `xfail` marker and its unused import were removed from the test. Nothing else was touched.
- The sandbox tests passed on the agent's branch (4 passed) and `ruff` was clean when checked out and run independently.
- Both failures were reported clearly on the issue and neither left a branch or a partial pull request behind.

## What went well

- The pipeline worked end to end on the first valid delivery: webhook, queue, Fargate task, GitHub App authentication, comment.
- Guardrails held: no code before `/approve`, no push outside `agent/issue-1`, no merge by the agent.
- Alarms and e-mail notifications worked the first time they were needed.
- Idle cost design held: nothing had to be kept running, and the tear-down left no billable resource.

## What went wrong

- The runbook had never been executed, and it showed: wrong status check name, an outdated place for the GitHub App private key, a step that would have put the AWS account ID in public workflow logs.
- A silent failure path exists between GitHub and the task table (finding 3).
- The image did not pin the tools it shares with target repositories.

## Action items

| Action | Type (prevent / detect / mitigate) | Owner | Status |
| --- | --- | --- | --- |
| Daily cost alarm without `SEARCH` ([#14](https://github.com/MaikonJm/ai-dev-agent/pull/14)) | prevent | Maikon | done |
| User-site scripts first on `PATH` in the runner image ([#15](https://github.com/MaikonJm/ai-dev-agent/pull/15)) | prevent | Maikon | done |
| Runbook rewritten after the session; default model Sonnet 4.6 ([#16](https://github.com/MaikonJm/ai-dev-agent/pull/16)) | prevent | Maikon | in review |
| `/revise` after a failed plan must return to the plan phase | prevent | Maikon | open |
| Alarm on webhook `401` responses, so a secret mismatch is not silent | detect | Maikon | open |
| Run the evaluation suite (`evals/`) on AWS and commit the results | detect | Maikon | open |

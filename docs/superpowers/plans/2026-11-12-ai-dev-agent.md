# AI Dev Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A serverless agent on AWS that turns a labeled GitHub issue into an approved plan and then a pull request with code, tests and a report.

**Architecture:** GitHub App webhook → API Gateway → `webhook` Lambda (verify, filter, record, enqueue) → SQS → `dispatcher` Lambda → ECS Fargate task running the agent (`runner`). The runner drives a hand-written agent loop on the Bedrock Converse API with sandboxed tools, stores state in DynamoDB and talks to GitHub with short-lived App tokens. Terraform builds everything; GitHub Actions tests, plans and pushes images via OIDC.

**Tech Stack:** Python 3.12, boto3, httpx, PyJWT (+cryptography), pytest, moto, ruff; Docker; Terraform ≥ 1.10 (AWS provider ~> 6.0); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-12-ai-dev-agent-design.md`

## Global Constraints

- No idle cost: only API Gateway, Lambda, SQS, DynamoDB (on-demand), ECS Fargate tasks on demand, ECR, SSM Parameter Store, CloudWatch. No NAT gateway, no always-on compute.
- Region `us-east-1`; resource name prefix `ai-dev-agent`.
- Terraform state in project 1's bucket (`backend.hcl` partial config, `use_lockfile = true`), new keys `ai-dev-agent/foundation.tfstate` and `ai-dev-agent/platform.tfstate`.
- Trigger label `agent`; commands `/approve` and `/revise <feedback>`; only users in `ALLOWED_USERS` may trigger.
- The agent never pushes to `main`; branches are `agent/issue-<number>`.
- Task states: `RECEIVED, PLANNING, AWAITING_APPROVAL, IMPLEMENTING, PR_OPENED, DONE, FAILED, BUDGET_EXCEEDED`.
- Default budgets per task: 40 tool iterations, 400k total tokens, 20 minutes, US$0.75.
- Command allowlist: `pytest`, `ruff`, `pip install -r requirements*.txt`, `git diff`, `git status`.
- Every comment, PR body and log line passes through redaction (secrets, 12-digit AWS account IDs).
- Model IDs come from configuration (`PLAN_MODEL_ID`, `IMPL_MODEL_ID`); defaults are Claude models on Bedrock (Haiku for plan, Sonnet for implement), confirmed against the account at deploy time.
- Public repositories: no secrets, account IDs or e-mails in code, docs, issues or PRs.

## Review Focus

- GitHub redelivers the same webhook (same `X-GitHub-Delivery`): the task must not run twice.
- `/approve` from a user not in the allowlist, or when the task is not `AWAITING_APPROVAL`: ignored with no side effects.
- The model asks to read or write `../` or an absolute path, or a symlink out of the repo: refused with a tool error, loop continues.
- The model passes shell metacharacters (`pytest; curl ...`) to `run_command`: refused; commands run with `shell=False` from a parsed argv.
- A budget runs out mid-implementation: state `BUDGET_EXCEEDED`, an explanatory issue comment, nothing pushed.

---

## File structure

```
ai-dev-agent/
  agent/
    config.py        # Settings dataclass from env
    budget.py        # Budget tracking and limits
    redact.py        # Secret/account-ID redaction
    tools.py         # Sandboxed tools (fs, search, commands)
    llm.py           # Bedrock Converse client + pricing; FakeLLM for tests
    loop.py          # Agent loop: run_phase(...)
    prompts.py       # System prompts for plan and implement phases
    github_app.py    # App JWT, installation token, issues/PR REST, git push
    store.py         # DynamoDB task records and state transitions
    metrics.py       # CloudWatch EMF metrics
    report.py        # Plan comment and PR body rendering
    runner.py        # Fargate entrypoint
  lambdas/
    webhook/app.py
    dispatcher/app.py
  tests/             # one test module per agent/ and lambdas/ module
  evals/
    cases.yaml
    run_evals.py
  Dockerfile
  pyproject.toml
  terraform/
    foundation/      # ECR, OIDC role, VPC (public subnets), SG egress 443
    platform/        # API GW, Lambdas, SQS+DLQ, DynamoDB, ECS, IAM, SSM, alarms, dashboard
  docs/  adr/  runbook.md
  .github/workflows/  ci.yml  terraform.yml  image.yml
agent-sandbox-shop/   # separate repository (Task 1)
```

---

### Task 1: Sandbox repository `agent-sandbox-shop`

**Files (in `/home/claude/agent-sandbox-shop`):**
- Create: `shop/main.py`, `shop/models.py`, `shop/cart.py`, `tests/test_products.py`, `tests/test_cart.py`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, `README.md`, `CONTRIBUTING.md`

**Interfaces:**
- Produces: FastAPI app `shop.main:app` with `GET /products`, `GET /products/{id}`, `POST /cart/{cart_id}/items`, `GET /cart/{cart_id}`; `shop.cart.cart_total(items: list[CartItem]) -> Decimal`.

- [ ] **Step 1: Write tests** for products and cart: `test_list_products_returns_seed_catalog` (3 seeded products), `test_get_unknown_product_returns_404`, `test_add_item_and_total` (2 × 19.90 + 1 × 5.00 → `Decimal("44.80")`).
- [ ] **Step 2: Implement** the app with an in-memory catalog; plant **the bug**: `cart_total` ignores quantity for the last item (so `test_add_item_and_total` is marked `xfail(reason="see issue #1")` in the repo).
- [ ] **Step 3: CI** runs `ruff check` and `pytest` on push and PR; `main` branch protection documented in README (set by Maikon in the UI).
- [ ] **Step 4: Run** `pytest -q` → passes with 1 xfailed; `ruff check .` → clean.
- [ ] **Step 5: Commit** directly to `main` (initial commit of an empty repo), push.
- [ ] **Step 6: Open the planted issues** via REST: #1 "Cart total ignores quantity of the last item" (bug), #2 "Add tests for product search by name" (tests; include the expected behavior), #3 "Add DELETE /cart/{cart_id}/items/{product_id}" (feature, with acceptance criteria). No `agent` label yet.

### Task 2: Agent package skeleton, config, budget, redaction

**Files:** Create `pyproject.toml`, `agent/__init__.py`, `agent/config.py`, `agent/budget.py`, `agent/redact.py`, `tests/test_config.py`, `tests/test_budget.py`, `tests/test_redact.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces:
  - `Settings.from_env() -> Settings` with fields `region, table_name, queue_url, plan_model_id, impl_model_id, allowed_users: frozenset[str], trigger_label="agent", max_iterations=40, max_tokens=400_000, max_seconds=1200, max_cost_usd=0.75, github_app_id, github_installation_id, github_repo, github_key_param, webhook_secret_param`.
  - `class Budget(max_iterations, max_tokens, max_seconds, max_cost_usd, clock=time.monotonic)`: `add_usage(input_tokens:int, output_tokens:int, cost_usd:float)`, `tick()`, `exceeded() -> str | None` (returns the limit name), `snapshot() -> dict`.
  - `redact(text: str) -> str`.

- [ ] **Step 1: Tests:** `test_settings_parses_allowed_users_csv`, `test_budget_reports_first_limit_hit` (iterations 2 → after 3 ticks `exceeded() == "iterations"`), `test_budget_time_limit_with_fake_clock`, `test_redact_account_id` (`"123456789012"` → `"<account-id>"`), `test_redact_github_tokens` (`ghs_…`, `github_pat_…`, `-----BEGIN RSA PRIVATE KEY-----` blocks → `<redacted>`), `test_redact_aws_keys` (`AKIA…` → `<redacted>`).
- [ ] **Step 2: Run** `pytest -q` → FAIL (modules missing).
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** `pytest -q && ruff check .` → PASS.
- [ ] **Step 5: CI** workflow: ruff + pytest on PR. Commit on branch `feat/skeleton`, PR, merge.

### Task 3: Sandboxed tools

**Files:** Create `agent/tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `redact` (Task 2).
- Produces: `class Workspace(root: Path, max_file_bytes=200_000, max_output_chars=12_000)` with methods `list_files(path=".") -> str`, `read_file(path) -> str`, `search_code(pattern: str) -> str`, `write_file(path, content) -> str`, `run_command(command: str) -> str`; `TOOL_SPECS: list[dict]` (Bedrock `toolSpec` JSON schemas for these five plus `finish`); `class ToolError(Exception)`; `dispatch(ws: Workspace, name: str, args: dict) -> str` (returns tool output or `"ERROR: ..."` instead of raising).

- [ ] **Step 1: Tests** (with `tmp_path`): `test_read_outside_root_refused` (`../x`, `/etc/passwd`, symlink to outside → `ToolError`), `test_write_creates_dirs_inside_root`, `test_write_over_limit_refused`, `test_run_command_allowlist` (`pytest -q` allowed; `curl x`, `pytest; rm -rf /`, `bash -c pytest` refused), `test_run_command_no_shell` (argv via `shlex.split`, `shell=False`, timeout 300 s), `test_output_truncated_and_redacted`, `test_dispatch_returns_error_string`, `test_search_code_uses_fixed_strings` (pattern with regex chars is literal).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**: resolve paths with `Path.resolve()` and require `is_relative_to(root)`; allowlist matches parsed argv prefixes; `pip install` only with `-r requirements*.txt`; `search_code` via Python walk (skip `.git`, binary files).
- [ ] **Step 4: Run** → PASS. **Step 5:** PR, merge.

### Task 4: LLM client with cost accounting

**Files:** Create `agent/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Produces: `@dataclass Turn(text: str, tool_calls: list[ToolCall], input_tokens: int, output_tokens: int, stop_reason: str)`; `@dataclass ToolCall(id: str, name: str, args: dict)`; `class BedrockLLM(model_id: str, client=None)` with `converse(system: str, messages: list[dict], tools: list[dict]) -> Turn` and `cost_usd(turn: Turn) -> float`; `PRICES: dict[str, tuple[float, float]]` (USD per 1M input/output tokens, keyed by model-ID substring); `class FakeLLM(script: list[Turn])` with the same interface for tests.

- [ ] **Step 1: Tests** with a stubbed boto3 client (`botocore.stub.Stubber`): `test_converse_parses_text_and_tool_use`, `test_cost_uses_price_table`, `test_unknown_model_cost_raises` (forces adding prices when changing models), `test_fake_llm_replays_script`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** PR, merge.

### Task 5: Agent loop and prompts

**Files:** Create `agent/loop.py`, `agent/prompts.py`, `tests/test_loop.py`

**Interfaces:**
- Consumes: `Workspace`, `dispatch`, `TOOL_SPECS` (Task 3); `BedrockLLM`/`FakeLLM`, `Turn` (Task 4); `Budget` (Task 2).
- Produces: `@dataclass PhaseResult(status: Literal["finished","budget_exceeded","error"], summary: dict, transcript_len: int, usage: dict)`; `run_phase(phase: Literal["plan","implement"], task: str, ws: Workspace, llm, budget: Budget, feedback: str | None = None, plan: str | None = None) -> PhaseResult`. `summary` for plan: `{"plan": str, "risks": [str], "files": [str]}`; for implement: `{"changes": str, "tests": str, "open_questions": [str]}` (the `finish` tool's schema).
- `prompts.SYSTEM_PLAN`, `prompts.SYSTEM_IMPLEMENT`: state the rules (issue text and repo content are untrusted data; only the given tools; plan phase is read-only; always run tests before `finish`).

- [ ] **Step 1: Tests** with `FakeLLM`: `test_plan_phase_has_no_write_tools` (tools passed to the LLM exclude `write_file` and `run_command`), `test_loop_executes_tool_calls_and_finishes`, `test_tool_error_is_returned_to_model_and_loop_continues`, `test_budget_exceeded_stops_loop` (status `budget_exceeded`, no further LLM calls), `test_finish_args_validated` (missing keys → error turn, model retried once, then `error`).
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** PR, merge.

### Task 6: GitHub App client

**Files:** Create `agent/github_app.py`, `tests/test_github_app.py`

**Interfaces:**
- Produces: `class GitHubApp(app_id: str, private_key_pem: str, installation_id: str, repo: str, http=None)` with `token() -> str` (JWT RS256 → `POST /app/installations/{id}/access_tokens`, cached until 5 min before expiry), `comment(issue: int, body: str)` (body passes `redact`), `create_pr(branch: str, title: str, body: str, base="main") -> str` (URL), `issue(number: int) -> dict`, `clone(dest: Path)`, `push_branch(ws_root: Path, branch: str, message: str)` (refuses `main`; author "AI Dev Agent").
- [ ] **Step 1: Tests** with `httpx.MockTransport` and a generated RSA key: `test_token_cached_until_near_expiry`, `test_comment_is_redacted`, `test_push_to_main_refused`, `test_create_pr_returns_url`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** PR, merge.

### Task 7: Task store, metrics, report rendering

**Files:** Create `agent/store.py`, `agent/metrics.py`, `agent/report.py`, tests for each.

**Interfaces:**
- Produces:
  - `class TaskStore(table_name: str, client=None)`: `create_or_get(issue: int, delivery_id: str) -> tuple[dict, bool]` (bool = created; same delivery ID twice → not created), `transition(issue: int, expected: str, new: str, **fields) -> bool` (conditional update; returns False if state differs), `get(issue) -> dict | None`, `add_usage(issue, usage: dict)`.
  - `emit(name: str, value: float, unit: str, dims: dict)` printing CloudWatch EMF JSON.
  - `render_plan_comment(issue: int, summary: dict, usage: dict) -> str`, `render_pr_body(issue: int, summary: dict, usage: dict, test_output: str) -> str` (both end with "Reply `/approve` or `/revise <feedback>`" or "Closes #N", and the usage line "tokens in/out · cost · duration").
- [ ] **Step 1: Tests** with `moto`: `test_duplicate_delivery_not_created`, `test_transition_conditional`, `test_emit_format`, `test_render_plan_has_commands`, `test_render_pr_closes_issue`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** PR, merge.

### Task 8: Runner (Fargate entrypoint) and Dockerfile

**Files:** Create `agent/runner.py`, `tests/test_runner.py`, `Dockerfile`, `.github/workflows/image.yml`

**Interfaces:**
- Consumes: everything in Tasks 2–7.
- Produces: `main(env: Mapping[str, str] = os.environ) -> int` reading `ISSUE_NUMBER`, `PHASE` (`plan|implement`), `FEEDBACK` (optional). Flow: load settings and secrets from SSM → `GitHubApp` → clone into `/work/repo` → `run_phase` → plan: comment plan, transition `PLANNING→AWAITING_APPROVAL`; implement: require tests passing in the final `run_command("pytest -q")`, `push_branch("agent/issue-N")`, `create_pr`, transition `IMPLEMENTING→PR_OPENED`; budget exceeded: comment + `BUDGET_EXCEEDED`; any exception: comment a redacted short error + `FAILED`. Emits metrics `TasksCompleted`, `TokensIn`, `TokensOut`, `CostUSD`, `DurationSeconds` with dimension `Outcome`.
- Dockerfile: `python:3.12-slim`, git installed, non-root user, `ENTRYPOINT ["python","-m","agent.runner"]`.
- [ ] **Step 1: Tests** with fakes for GitHub/LLM/store: `test_plan_flow_comments_and_waits`, `test_implement_flow_opens_pr`, `test_implement_refuses_pr_when_tests_fail`, `test_budget_exceeded_comments_and_pushes_nothing`, `test_unexpected_error_marks_failed_and_redacts`.
- [ ] **Step 2–4:** fail → implement → pass. `docker build .` succeeds locally if Docker is available (else CI).
- [ ] **Step 5:** image workflow builds on PR and pushes to ECR on `main` via OIDC (skips existing tags, like project 1). PR, merge.

### Task 9: Lambdas: webhook and dispatcher

**Files:** Create `lambdas/webhook/app.py`, `lambdas/dispatcher/app.py`, `tests/test_webhook.py`, `tests/test_dispatcher.py`

**Interfaces:**
- Consumes: `TaskStore`, `Settings`, `redact`.
- Produces: `webhook.handler(event, context) -> dict` (API Gateway HTTP API v2 payload) and `dispatcher.handler(event, context) -> dict` (SQS batch, `batchItemFailures`). Queue message: `{"issue": int, "phase": "plan"|"implement", "feedback": str|None, "delivery": str}`.
- Webhook rules: verify `X-Hub-Signature-256` (HMAC SHA-256, constant-time); accept `issues.labeled` with label `agent` → `RECEIVED→PLANNING`, enqueue plan; `issue_comment.created` with body starting `/approve` and state `AWAITING_APPROVAL` → `IMPLEMENTING`, enqueue implement; `/revise <text>` → back to `PLANNING` (or `IMPLEMENTING` if a PR exists) with feedback; sender must be in `allowed_users`; everything else → 204 no-op. Dispatcher calls `ecs.run_task` (Fargate, public IP, task definition and subnets from env) with container overrides `ISSUE_NUMBER`, `PHASE`, `FEEDBACK`.
- [ ] **Step 1: Tests**: `test_bad_signature_401`, `test_duplicate_delivery_ignored`, `test_label_from_disallowed_user_ignored`, `test_approve_only_when_awaiting`, `test_revise_carries_feedback`, `test_dispatcher_runs_task_with_overrides`, `test_dispatcher_reports_partial_failures`.
- [ ] **Step 2–4:** fail → implement → pass. **Step 5:** PR, merge.

### Task 10: Terraform foundation

**Files:** Create `terraform/foundation/{versions.tf,variables.tf,main.tf,network.tf,ecr.tf,github-oidc.tf,outputs.tf,backend.hcl.example}`, `.github/workflows/terraform.yml`

**Interfaces:**
- Produces outputs: `ecr_repository_url`, `subnet_ids`, `sandbox_security_group_id`, `ci_role_arn`.
- Contents: VPC `10.30.0.0/16`, 2 public subnets, IGW, S3 gateway endpoint; SG for sandbox with no ingress and egress TCP 443 only; ECR `ai-dev-agent/runner` (immutable, scan on push, keep last 10); OIDC role trusting `repo:MaikonJm@<owner-id>/ai-dev-agent@<repo-id>:*` (immutable subject format from project 1, IDs as variables), read-only + ECR push + state access.
- [ ] **Step 1:** `terraform fmt -check` and `terraform validate` in CI (matrix over stacks). **Step 2:** PR, merge. Apply happens in the test session.

### Task 11: Terraform platform

**Files:** Create `terraform/platform/{versions.tf,variables.tf,main.tf,api.tf,lambdas.tf,queue.tf,table.tf,ecs.tf,iam.tf,ssm.tf,observability.tf,outputs.tf,backend.hcl.example,terraform.tfvars.example}`

**Interfaces:**
- Consumes: foundation outputs via `terraform_remote_state`.
- Produces outputs: `webhook_url`, `table_name`, `queue_url`, `dashboard_url`.
- Contents: HTTP API with one route `POST /github/webhook`; two Lambdas packaged with `archive_file` (Python 3.12, X-Ray active); SQS `jobs` with DLQ (`maxReceiveCount` 3) and visibility 900 s; DynamoDB on-demand table keyed by `issue` (Number) with TTL on `expires_at`; ECS cluster + Fargate task definition (0.5 vCPU, 1 GB, ephemeral storage default), log group 14 days; IAM: webhook (SSM read of webhook secret, DynamoDB, SQS send), dispatcher (SQS consume, `ecs:RunTask`, `iam:PassRole` on the two task roles), task role (Bedrock invoke on the two model IDs, DynamoDB item access on its table, SSM read of the App key, CloudWatch PutMetricData); SSM SecureString parameters created empty-ish with `lifecycle { ignore_changes = [value] }` so values are set in the console; alarms: DLQ not empty, `Outcome=FAILED` > 0, monthly `CostUSD` sum > 5 → existing SNS topic from project 1 if present, else a new one; dashboard with tasks by outcome, cost, tokens, duration.
- [ ] **Step 1:** fmt/validate in CI. **Step 2:** PR, merge.

### Task 12: Evaluations

**Files:** Create `evals/cases.yaml`, `evals/run_evals.py`, `evals/README.md`, `tests/test_evals.py`

**Interfaces:**
- Produces: `run_evals.py --repo MaikonJm/agent-sandbox-shop --cases evals/cases.yaml --out evals/results/<date>.json`: for each case, opens an issue from the case text with label `agent`, waits for the plan, posts `/approve`, waits for the PR, checks out the PR branch and runs the case's hidden acceptance test; records `passed`, cost, tokens, duration. `summarize(results: list[dict]) -> dict` (success rate, mean/max cost, mean duration).
- Cases: the three planted issues from Task 1 plus two more (an input-validation bug and a refactor with tests).
- [ ] **Step 1:** unit test `summarize`; **Step 2:** PR, merge. Real runs happen in the test session.

### Task 13: Documentation

**Files:** Modify `README.md`; create `docs/adr/0001-serverless-fargate-sandbox.md`, `docs/adr/0002-own-agent-loop.md`, `docs/adr/0003-github-app-auth.md`, `docs/runbook.md`, `docs/postmortems/TEMPLATE.md`, `docs/diagrams/architecture.py` (same hand-laid style as project 1) and `docs/images/architecture.png`.

- [ ] **Step 1:** README: what it is, diagram, flow, guardrails table, costs, step-by-step setup (create GitHub App in the UI with exact permissions; store key and webhook secret in Parameter Store via console; enable Bedrock model access; apply foundation, platform; set webhook URL), how to run evals, roadmap.
- [ ] **Step 2:** PR, merge.

---

## Execution order

Task 1 (sandbox repo) is independent. Tasks 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 build on each other. Tasks 10–11 can follow Task 9. Tasks 12–13 last. The AWS test session (apply, GitHub App, Bedrock access, evals) is a separate step after the merge of Task 13.

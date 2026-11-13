"""Runtime settings, read from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    region: str = "us-east-1"
    table_name: str = "ai-dev-agent-tasks"
    queue_url: str = ""
    plan_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    impl_model_id: str = "us.anthropic.claude-sonnet-4-6"
    allowed_users: frozenset[str] = frozenset()
    trigger_label: str = "agent"
    max_iterations: int = 40
    max_tokens: int = 400_000
    max_seconds: int = 1200
    max_cost_usd: float = 0.75
    github_app_id: str = ""
    github_installation_id: str = ""
    github_repo: str = ""
    github_key_param: str = "/ai-dev-agent/github-app-private-key"
    webhook_secret_param: str = "/ai-dev-agent/github-webhook-secret"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()

        def get(name: str, default):
            return env.get(name, default)

        users = get("ALLOWED_USERS", "")
        return cls(
            region=get("AWS_REGION", d.region),
            table_name=get("TABLE_NAME", d.table_name),
            queue_url=get("QUEUE_URL", d.queue_url),
            plan_model_id=get("PLAN_MODEL_ID", d.plan_model_id),
            impl_model_id=get("IMPL_MODEL_ID", d.impl_model_id),
            allowed_users=frozenset(u.strip().lower() for u in users.split(",") if u.strip()),
            trigger_label=get("TRIGGER_LABEL", d.trigger_label),
            max_iterations=int(get("MAX_ITERATIONS", d.max_iterations)),
            max_tokens=int(get("MAX_TOKENS", d.max_tokens)),
            max_seconds=int(get("MAX_SECONDS", d.max_seconds)),
            max_cost_usd=float(get("MAX_COST_USD", d.max_cost_usd)),
            github_app_id=get("GITHUB_APP_ID", d.github_app_id),
            github_installation_id=get("GITHUB_INSTALLATION_ID", d.github_installation_id),
            github_repo=get("GITHUB_REPO", d.github_repo),
            github_key_param=get("GITHUB_KEY_PARAM", d.github_key_param),
            webhook_secret_param=get("WEBHOOK_SECRET_PARAM", d.webhook_secret_param),
        )

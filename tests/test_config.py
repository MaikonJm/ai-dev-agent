from agent.config import Settings


def test_settings_parses_allowed_users_csv():
    s = Settings.from_env({"ALLOWED_USERS": "MaikonJm, other ", "GITHUB_REPO": "o/r"})
    assert s.allowed_users == frozenset({"maikonjm", "other"})
    assert s.trigger_label == "agent"
    assert s.max_iterations == 40 and s.max_tokens == 400_000
    assert s.max_seconds == 1200 and s.max_cost_usd == 0.75


def test_settings_overrides_budgets():
    s = Settings.from_env({"MAX_ITERATIONS": "5", "MAX_COST_USD": "0.1"})
    assert s.max_iterations == 5 and s.max_cost_usd == 0.1

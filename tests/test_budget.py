from agent.budget import Budget


def test_budget_reports_first_limit_hit():
    b = Budget(max_iterations=2, max_tokens=1000, max_seconds=60, max_cost_usd=1.0)
    for _ in range(3):
        b.tick()
    assert b.exceeded() == "iterations"


def test_budget_tokens_and_cost():
    b = Budget(max_iterations=10, max_tokens=100, max_seconds=60, max_cost_usd=1.0)
    b.add_usage(60, 50, 0.01)
    assert b.exceeded() == "tokens"
    c = Budget(max_iterations=10, max_tokens=10_000, max_seconds=60, max_cost_usd=0.05)
    c.add_usage(10, 10, 0.06)
    assert c.exceeded() == "cost"


def test_budget_time_limit_with_fake_clock():
    now = [100.0]
    b = Budget(max_iterations=10, max_tokens=1000, max_seconds=30, max_cost_usd=1.0, clock=lambda: now[0])
    assert b.exceeded() is None
    now[0] = 131.0
    assert b.exceeded() == "time"


def test_snapshot_has_usage():
    b = Budget(max_iterations=10, max_tokens=1000, max_seconds=30, max_cost_usd=1.0)
    b.add_usage(3, 4, 0.5)
    b.tick()
    snap = b.snapshot()
    assert snap["input_tokens"] == 3 and snap["output_tokens"] == 4
    assert snap["cost_usd"] == 0.5 and snap["iterations"] == 1

import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agent.github_app import GitHubApp

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()).decode()


def make_app(handler, now):
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    return GitHubApp("123", PEM, "456", "o/r", http=client, clock=lambda: now[0])


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_token_cached_until_near_expiry():
    now = [datetime(2026, 11, 13, 12, 0, tzinfo=UTC)]
    calls = []

    def handler(request):
        calls.append(request)
        claims = jwt.decode(request.headers["Authorization"].split()[1], KEY.public_key(), algorithms=["RS256"],
                            options={"verify_iat": False, "verify_exp": False})
        assert claims["iss"] == "123"
        return httpx.Response(201, json={"token": f"ghs_t{len(calls)}", "expires_at": iso(now[0] + timedelta(hours=1))})

    app = make_app(handler, now)
    assert app.token() == "ghs_t1" and app.token() == "ghs_t1"
    now[0] += timedelta(minutes=56)
    assert app.token() == "ghs_t2"
    assert calls[0].url.path == "/app/installations/456/access_tokens"


def _router(now, seen):
    def handler(request):
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "ghs_x", "expires_at": iso(now[0] + timedelta(hours=1))})
        seen.append(request)
        if request.url.path == "/repos/o/r/pulls":
            return httpx.Response(201, json={"html_url": "https://github.com/o/r/pull/7"})
        if request.url.path == "/repos/o/r/issues/5":
            return httpx.Response(200, json={"number": 5, "title": "T", "body": "B"})
        return httpx.Response(201, json={})
    return handler


def test_comment_is_redacted():
    now, seen = [datetime(2026, 11, 13, tzinfo=UTC)], []
    app = make_app(_router(now, seen), now)
    app.comment(5, "arn:aws:iam::123456789012:role/x")
    body = json.loads(seen[0].content)["body"]
    assert "123456789012" not in body and "<account-id>" in body
    assert seen[0].headers["Authorization"] == "Bearer ghs_x"


def test_create_pr_returns_url_and_redacts():
    now, seen = [datetime(2026, 11, 13, tzinfo=UTC)], []
    app = make_app(_router(now, seen), now)
    assert app.create_pr("agent/issue-5", "Fix", "key AKIAIOSFODNN7EXAMPLE") == "https://github.com/o/r/pull/7"
    payload = json.loads(seen[0].content)
    assert payload["head"] == "agent/issue-5" and payload["base"] == "main" and "AKIA" not in payload["body"]


def test_issue_returns_json():
    now, seen = [datetime(2026, 11, 13, tzinfo=UTC)], []
    assert make_app(_router(now, seen), now).issue(5)["title"] == "T"


@pytest.mark.parametrize("branch", ["main", "master", "refs/heads/main"])
def test_push_to_main_refused(tmp_path, branch):
    now = [datetime(2026, 11, 13, tzinfo=UTC)]
    with pytest.raises(ValueError):
        make_app(lambda r: httpx.Response(500), now).push_branch(tmp_path, branch, "msg")

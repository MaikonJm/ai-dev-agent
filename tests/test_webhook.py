import hashlib
import hmac
import json

import pytest

from agent.config import Settings
from lambdas.webhook import app

SECRET = "s3cret"


class FakeStore:
    def __init__(self):
        self.items, self.deliveries = {}, set()

    def create_or_get(self, issue, delivery):
        created = issue not in self.items
        if created:
            self.items[issue] = {"issue": issue, "state": "RECEIVED"}
        self.deliveries.add((issue, delivery))
        return dict(self.items[issue]), created

    def seen_delivery(self, issue, delivery):
        return (issue, delivery) in self.deliveries

    def mark_delivery(self, issue, delivery):
        self.deliveries.add((issue, delivery))

    def get(self, issue):
        return self.items.get(issue)

    def transition(self, issue, expected, new, **fields):
        item = self.items.get(issue)
        if not item or item["state"] != expected:
            return False
        item.update(state=new, **fields)
        return True


@pytest.fixture
def env(monkeypatch):
    store, sent = FakeStore(), []
    monkeypatch.setattr(app, "_deps", lambda: (Settings(allowed_users=frozenset({"maikonjm"})), store,
                                               lambda msg: sent.append(msg), SECRET))
    return store, sent


def event(kind, payload, delivery="d1", secret=SECRET):
    body = json.dumps(payload)
    sig = "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return {"headers": {"x-github-event": kind, "x-github-delivery": delivery, "x-hub-signature-256": sig},
            "body": body, "isBase64Encoded": False}


def labeled(user="MaikonJm", label="agent"):
    return {"action": "labeled", "label": {"name": label}, "issue": {"number": 5}, "sender": {"login": user}}


def comment(text, user="MaikonJm"):
    return {"action": "created", "issue": {"number": 5}, "comment": {"body": text}, "sender": {"login": user}}


def test_bad_signature_401(env):
    assert app.handler(event("issues", labeled(), secret="wrong"), None)["statusCode"] == 401


def test_label_starts_planning(env):
    store, sent = env
    assert app.handler(event("issues", labeled()), None)["statusCode"] == 202
    assert store.items[5]["state"] == "PLANNING"
    assert sent == [{"issue": 5, "phase": "plan", "feedback": None, "delivery": "d1"}]


def test_duplicate_delivery_ignored(env):
    store, sent = env
    app.handler(event("issues", labeled()), None)
    assert app.handler(event("issues", labeled()), None)["statusCode"] == 200
    assert len(sent) == 1


def test_label_from_disallowed_user_ignored(env):
    store, sent = env
    assert app.handler(event("issues", labeled(user="stranger")), None)["statusCode"] == 204
    assert not sent and not store.items


def test_other_label_ignored(env):
    _, sent = env
    assert app.handler(event("issues", labeled(label="bug")), None)["statusCode"] == 204 and not sent


def test_approve_only_when_awaiting(env):
    store, sent = env
    store.items[5] = {"issue": 5, "state": "PLANNING"}
    assert app.handler(event("issue_comment", comment("/approve"), "d2"), None)["statusCode"] == 204
    store.items[5]["state"] = "AWAITING_APPROVAL"
    assert app.handler(event("issue_comment", comment("/approve"), "d3"), None)["statusCode"] == 202
    assert store.items[5]["state"] == "IMPLEMENTING" and sent[-1]["phase"] == "implement"


def test_approve_from_disallowed_user_ignored(env):
    store, sent = env
    store.items[5] = {"issue": 5, "state": "AWAITING_APPROVAL"}
    app.handler(event("issue_comment", comment("/approve", user="stranger"), "d2"), None)
    assert store.items[5]["state"] == "AWAITING_APPROVAL" and not sent


def test_revise_carries_feedback(env):
    store, sent = env
    store.items[5] = {"issue": 5, "state": "AWAITING_APPROVAL"}
    assert app.handler(event("issue_comment", comment("/revise also cover search"), "d4"), None)["statusCode"] == 202
    assert store.items[5]["state"] == "PLANNING"
    assert sent[-1] == {"issue": 5, "phase": "plan", "feedback": "also cover search", "delivery": "d4"}


def test_revise_after_pr_reimplements(env):
    store, sent = env
    store.items[5] = {"issue": 5, "state": "PR_OPENED", "plan": "{}"}
    app.handler(event("issue_comment", comment("/revise rename the test"), "d5"), None)
    assert store.items[5]["state"] == "IMPLEMENTING" and sent[-1]["phase"] == "implement"


def test_plain_comment_ignored(env):
    store, sent = env
    store.items[5] = {"issue": 5, "state": "AWAITING_APPROVAL"}
    assert app.handler(event("issue_comment", comment("looks good"), "d6"), None)["statusCode"] == 204

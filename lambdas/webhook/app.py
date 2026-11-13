"""GitHub webhook → task state → SQS job. Verifies, filters and deduplicates every delivery."""

import base64
import functools
import hashlib
import hmac
import json

from agent.config import Settings

REVISE_FROM = [("AWAITING_APPROVAL", "PLANNING", "plan"), ("PR_OPENED", "IMPLEMENTING", "implement"),
               ("FAILED", "IMPLEMENTING", "implement"), ("BUDGET_EXCEEDED", "IMPLEMENTING", "implement")]


@functools.cache
def _deps():  # pragma: no cover - AWS wiring, replaced in tests
    import boto3

    from agent.store import TaskStore

    settings = Settings.from_env()
    secret = boto3.client("ssm").get_parameter(Name=settings.webhook_secret_param,
                                               WithDecryption=True)["Parameter"]["Value"]
    sqs = boto3.client("sqs")

    def send(message: dict) -> None:
        sqs.send_message(QueueUrl=settings.queue_url, MessageBody=json.dumps(message))

    return settings, TaskStore(settings.table_name), send, secret


def _response(status: int, msg: str) -> dict:
    print(json.dumps({"level": "INFO", "status": status, "msg": msg}))
    return {"statusCode": status, "body": json.dumps({"msg": msg})}


def _valid(secret: str, body: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def handler(event, context):
    settings, store, send, secret = _deps()
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw = event.get("body") or ""
    body = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()
    if not _valid(secret, body, headers.get("x-hub-signature-256", "")):
        return _response(401, "invalid signature")

    kind, delivery = headers.get("x-github-event"), headers.get("x-github-delivery", "")
    payload = json.loads(body)
    sender = (payload.get("sender") or {}).get("login", "").lower()
    if sender not in settings.allowed_users:
        return _response(204, f"sender {sender or '?'} not allowed")
    issue = (payload.get("issue") or {}).get("number")
    if not issue:
        return _response(204, "no issue")

    if kind == "issues" and payload.get("action") == "labeled":
        if (payload.get("label") or {}).get("name") != settings.trigger_label:
            return _response(204, "other label")
        if store.seen_delivery(issue, delivery):
            return _response(200, "duplicate delivery")
        _, created = store.create_or_get(issue, delivery)
        if not created or not store.transition(issue, "RECEIVED", "PLANNING"):
            return _response(200, "task already exists")
        send({"issue": issue, "phase": "plan", "feedback": None, "delivery": delivery})
        return _response(202, "planning")

    if kind == "issue_comment" and payload.get("action") == "created" and not payload["issue"].get("pull_request"):
        text = (payload.get("comment") or {}).get("body", "").strip()
        if not text.startswith(("/approve", "/revise")):
            return _response(204, "not a command")
        if store.seen_delivery(issue, delivery):
            return _response(200, "duplicate delivery")
        store.mark_delivery(issue, delivery)
        if text.startswith("/approve"):
            if store.transition(issue, "AWAITING_APPROVAL", "IMPLEMENTING"):
                send({"issue": issue, "phase": "implement", "feedback": None, "delivery": delivery})
                return _response(202, "implementing")
            return _response(204, "nothing awaiting approval")
        feedback = text.removeprefix("/revise").strip()[:2000] or None
        for expected, new, phase in REVISE_FROM:
            if store.transition(issue, expected, new, feedback=feedback or ""):
                send({"issue": issue, "phase": phase, "feedback": feedback, "delivery": delivery})
                return _response(202, f"revising ({phase})")
        return _response(204, "nothing to revise")

    return _response(204, f"ignored {kind}")

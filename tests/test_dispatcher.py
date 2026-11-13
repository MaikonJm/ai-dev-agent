import json

from lambdas.dispatcher import app


class FakeECS:
    def __init__(self, fail_issue=None):
        self.calls, self.fail_issue = [], fail_issue

    def run_task(self, **kwargs):
        self.calls.append(kwargs)
        env = {e["name"]: e["value"] for e in kwargs["overrides"]["containerOverrides"][0]["environment"]}
        if env["ISSUE_NUMBER"] == str(self.fail_issue):
            return {"tasks": [], "failures": [{"reason": "RESOURCE:CPU"}]}
        return {"tasks": [{"taskArn": "arn"}], "failures": []}


ENV = {"CLUSTER": "c", "TASK_DEFINITION": "td", "SUBNETS": "s1,s2", "SECURITY_GROUP": "sg", "CONTAINER_NAME": "agent"}


def record(i, issue, phase="plan", feedback=None):
    return {"messageId": f"m{i}", "body": json.dumps({"issue": issue, "phase": phase, "feedback": feedback,
                                                     "delivery": "d"})}


def test_dispatcher_runs_task_with_overrides(monkeypatch):
    ecs = FakeECS()
    monkeypatch.setattr(app, "_ecs", lambda: ecs)
    monkeypatch.setattr(app.os, "environ", ENV)
    out = app.handler({"Records": [record(1, 5, "implement", "more tests")]}, None)
    assert out == {"batchItemFailures": []}
    call = ecs.calls[0]
    assert call["launchType"] == "FARGATE" and call["taskDefinition"] == "td"
    net = call["networkConfiguration"]["awsvpcConfiguration"]
    assert net["subnets"] == ["s1", "s2"] and net["assignPublicIp"] == "ENABLED"
    env = {e["name"]: e["value"] for e in call["overrides"]["containerOverrides"][0]["environment"]}
    assert env == {"ISSUE_NUMBER": "5", "PHASE": "implement", "FEEDBACK": "more tests"}


def test_dispatcher_reports_partial_failures(monkeypatch):
    ecs = FakeECS(fail_issue=6)
    monkeypatch.setattr(app, "_ecs", lambda: ecs)
    monkeypatch.setattr(app.os, "environ", ENV)
    out = app.handler({"Records": [record(1, 5), record(2, 6), {"messageId": "m3", "body": "not json"}]}, None)
    assert out == {"batchItemFailures": [{"itemIdentifier": "m2"}, {"itemIdentifier": "m3"}]}

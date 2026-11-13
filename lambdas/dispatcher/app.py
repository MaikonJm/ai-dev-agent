"""SQS job → one ECS Fargate task running the agent. Failed records go back to the queue (then the DLQ)."""

import json
import os


def _ecs():  # pragma: no cover - replaced in tests
    import boto3

    return boto3.client("ecs")


def handler(event, context):
    env, ecs, failures = os.environ, _ecs(), []
    for record in event.get("Records", []):
        try:
            job = json.loads(record["body"])
            overrides = [{"name": "ISSUE_NUMBER", "value": str(int(job["issue"]))},
                         {"name": "PHASE", "value": job["phase"]}]
            if job.get("feedback"):
                overrides.append({"name": "FEEDBACK", "value": job["feedback"][:2000]})
            result = ecs.run_task(
                cluster=env["CLUSTER"], taskDefinition=env["TASK_DEFINITION"], launchType="FARGATE", count=1,
                networkConfiguration={"awsvpcConfiguration": {"subnets": env["SUBNETS"].split(","),
                                                              "securityGroups": [env["SECURITY_GROUP"]],
                                                              "assignPublicIp": "ENABLED"}},
                overrides={"containerOverrides": [{"name": env["CONTAINER_NAME"], "environment": overrides}]},
            )
            if result.get("failures") or not result.get("tasks"):
                raise RuntimeError(f"run_task failed: {result.get('failures')}")
            print(json.dumps({"level": "INFO", "msg": "task started", "issue": job["issue"], "phase": job["phase"]}))
        except Exception as exc:  # noqa: BLE001 - report per record, never fail the whole batch
            print(json.dumps({"level": "ERROR", "msg": str(exc)[:300], "messageId": record.get("messageId")}))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}

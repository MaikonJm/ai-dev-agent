"""Task records in DynamoDB, one per issue, with conditional state transitions."""

import time
from decimal import Decimal

import boto3

TTL_DAYS = 30


def _plain(value: dict) -> object:
    (kind, raw), = value.items()
    if kind == "N":
        number = Decimal(raw)
        return int(number) if number == number.to_integral_value() else float(number)
    if kind == "SS":
        return set(raw)
    return raw


class TaskStore:
    def __init__(self, table_name: str, client=None, region: str = "us-east-1"):
        self.table = table_name
        self.db = client or boto3.client("dynamodb", region_name=region)

    def get(self, issue: int) -> dict | None:
        item = self.db.get_item(TableName=self.table, Key={"issue": {"N": str(issue)}}, ConsistentRead=True).get("Item")
        return {k: _plain(v) for k, v in item.items()} if item else None

    def create_or_get(self, issue: int, delivery_id: str) -> tuple[dict, bool]:
        now = int(time.time())
        try:
            self.db.put_item(
                TableName=self.table,
                Item={"issue": {"N": str(issue)}, "state": {"S": "RECEIVED"}, "deliveries": {"SS": [delivery_id]},
                      "created_at": {"N": str(now)}, "updated_at": {"N": str(now)},
                      "expires_at": {"N": str(now + TTL_DAYS * 86400)},
                      "input_tokens": {"N": "0"}, "output_tokens": {"N": "0"}, "cost_usd": {"N": "0"}},
                ConditionExpression="attribute_not_exists(issue)")
            return self.get(issue), True
        except self.db.exceptions.ConditionalCheckFailedException:
            return self.get(issue), False

    def seen_delivery(self, issue: int, delivery_id: str) -> bool:
        item = self.get(issue)
        return bool(item) and delivery_id in item.get("deliveries", set())

    def mark_delivery(self, issue: int, delivery_id: str) -> None:
        self.db.update_item(TableName=self.table, Key={"issue": {"N": str(issue)}},
                            UpdateExpression="ADD deliveries :d",
                            ExpressionAttributeValues={":d": {"SS": [delivery_id]}})

    def transition(self, issue: int, expected: str, new: str, **fields) -> bool:
        names = {"#s": "state", "#u": "updated_at"}
        values = {":expected": {"S": expected}, ":new": {"S": new}, ":now": {"N": str(int(time.time()))}}
        sets = ["#s = :new", "#u = :now"]
        for i, (key, value) in enumerate(fields.items()):
            names[f"#f{i}"] = key
            values[f":f{i}"] = {"N": str(value)} if isinstance(value, int | float) else {"S": str(value)}
            sets.append(f"#f{i} = :f{i}")
        try:
            self.db.update_item(TableName=self.table, Key={"issue": {"N": str(issue)}},
                                UpdateExpression="SET " + ", ".join(sets), ConditionExpression="#s = :expected",
                                ExpressionAttributeNames=names, ExpressionAttributeValues=values)
            return True
        except self.db.exceptions.ConditionalCheckFailedException:
            return False

    def add_usage(self, issue: int, usage: dict) -> None:
        self.db.update_item(
            TableName=self.table, Key={"issue": {"N": str(issue)}},
            UpdateExpression="ADD input_tokens :i, output_tokens :o, cost_usd :c",
            ExpressionAttributeValues={":i": {"N": str(usage.get("input_tokens", 0))},
                                       ":o": {"N": str(usage.get("output_tokens", 0))},
                                       ":c": {"N": str(usage.get("cost_usd", 0))}})

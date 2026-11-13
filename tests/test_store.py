import boto3
import pytest
from moto import mock_aws

from agent.store import TaskStore


@pytest.fixture
def store():
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(TableName="t", KeySchema=[{"AttributeName": "issue", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "issue", "AttributeType": "N"}],
                         BillingMode="PAY_PER_REQUEST")
        yield TaskStore("t", client=ddb)


def test_create_or_get_creates_once(store):
    item, created = store.create_or_get(5, "d1")
    assert created and item["state"] == "RECEIVED"
    _, created_again = store.create_or_get(5, "d2")
    assert not created_again


def test_duplicate_delivery_detected(store):
    store.create_or_get(5, "d1")
    assert store.seen_delivery(5, "d1") and not store.seen_delivery(5, "d9")
    store.mark_delivery(5, "d9")
    assert store.seen_delivery(5, "d9")


def test_transition_conditional(store):
    store.create_or_get(5, "d1")
    assert store.transition(5, "RECEIVED", "PLANNING", feedback="x")
    assert not store.transition(5, "RECEIVED", "PLANNING")
    item = store.get(5)
    assert item["state"] == "PLANNING" and item["feedback"] == "x"


def test_add_usage_accumulates(store):
    store.create_or_get(5, "d1")
    store.add_usage(5, {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01})
    store.add_usage(5, {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.02})
    item = store.get(5)
    assert item["input_tokens"] == 11 and item["output_tokens"] == 6
    assert item["cost_usd"] == pytest.approx(0.03)


def test_get_missing_returns_none(store):
    assert store.get(99) is None

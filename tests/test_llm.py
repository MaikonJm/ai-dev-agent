import boto3
import pytest
from botocore.stub import ANY, Stubber

from agent.llm import BedrockLLM, FakeLLM, ToolCall, Turn

MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


def _client():
    return boto3.client("bedrock-runtime", region_name="us-east-1", aws_access_key_id="x",
                        aws_secret_access_key="x")


def test_converse_parses_text_and_tool_use():
    client = _client()
    stub = Stubber(client)
    stub.add_response("converse", {
        "output": {"message": {"role": "assistant", "content": [
            {"text": "Let me look."},
            {"toolUse": {"toolUseId": "t1", "name": "read_file", "input": {"path": "a.py"}}},
        ]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1000, "outputTokens": 200, "totalTokens": 1200},
        "metrics": {"latencyMs": 50},
    }, {"modelId": MODEL, "system": ANY, "messages": ANY, "toolConfig": ANY, "inferenceConfig": ANY})
    with stub:
        tools = [{"toolSpec": {"name": "read_file", "inputSchema": {"json": {"type": "object"}}}}]
        turn = BedrockLLM(MODEL, client=client).converse("sys", [{"role": "user", "content": [{"text": "hi"}]}], tools)
    assert turn.text == "Let me look."
    assert turn.tool_calls == [ToolCall(id="t1", name="read_file", args={"path": "a.py"})]
    assert (turn.input_tokens, turn.output_tokens, turn.stop_reason) == (1000, 200, "tool_use")
    assert turn.raw_content[1]["toolUse"]["toolUseId"] == "t1"


def test_cost_uses_price_table():
    turn = Turn(text="", tool_calls=[], input_tokens=1_000_000, output_tokens=1_000_000, stop_reason="end_turn")
    assert BedrockLLM(MODEL, client=object()).cost_usd(turn) == pytest.approx(3.0 + 15.0)


def test_unknown_model_cost_raises():
    with pytest.raises(KeyError):
        BedrockLLM("some.unknown-model", client=object())


def test_fake_llm_replays_script():
    t1 = Turn(text="a", tool_calls=[], input_tokens=1, output_tokens=1, stop_reason="end_turn")
    fake = FakeLLM([t1])
    assert fake.converse("s", [], []) is t1
    assert fake.calls[0]["system"] == "s"
    assert fake.cost_usd(t1) == 0.0
    with pytest.raises(AssertionError):
        fake.converse("s", [], [])

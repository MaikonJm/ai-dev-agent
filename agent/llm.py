"""Thin client over the Bedrock Converse API, with token and cost accounting."""

from dataclasses import dataclass, field

import boto3

# USD per 1M input / output tokens, matched by substring of the model ID.
# Check https://aws.amazon.com/bedrock/pricing/ when changing models.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "nova-pro": (0.8, 3.2),
    "nova-lite": (0.06, 0.24),
    "nova-micro": (0.035, 0.14),
}


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    stop_reason: str
    raw_content: list[dict] = field(default_factory=list)


def _price(model_id: str) -> tuple[float, float]:
    for key, price in PRICES.items():
        if key in model_id:
            return price
    raise KeyError(f"no price for model {model_id}; add it to agent.llm.PRICES")


class BedrockLLM:
    def __init__(self, model_id: str, client=None, region: str = "us-east-1", max_output_tokens: int = 4096):
        self.model_id = model_id
        self._price = _price(model_id)
        self.client = client or boto3.client("bedrock-runtime", region_name=region)
        self.max_output_tokens = max_output_tokens

    def converse(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=messages,
            toolConfig={"tools": tools},
            inferenceConfig={"maxTokens": self.max_output_tokens, "temperature": 0.2},
        )
        content = response["output"]["message"]["content"]
        text = "\n".join(block["text"] for block in content if "text" in block)
        calls = [ToolCall(id=b["toolUse"]["toolUseId"], name=b["toolUse"]["name"], args=b["toolUse"]["input"])
                 for b in content if "toolUse" in b]
        usage = response["usage"]
        return Turn(text=text, tool_calls=calls, input_tokens=usage["inputTokens"],
                    output_tokens=usage["outputTokens"], stop_reason=response["stopReason"], raw_content=content)

    def cost_usd(self, turn: Turn) -> float:
        price_in, price_out = self._price
        return (turn.input_tokens * price_in + turn.output_tokens * price_out) / 1_000_000


class FakeLLM:
    """Replays scripted turns; records what it was called with. For tests and dry runs."""

    def __init__(self, script: list[Turn]):
        self.script = list(script)
        self.calls: list[dict] = []
        self.model_id = "fake"

    def converse(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        assert self.script, "FakeLLM script exhausted"
        return self.script.pop(0)

    def cost_usd(self, turn: Turn) -> float:
        return 0.0

"""Per-task limits: iterations, tokens, wall-clock time and cost."""

import time
from collections.abc import Callable


class Budget:
    def __init__(self, max_iterations: int, max_tokens: int, max_seconds: float, max_cost_usd: float,
                 clock: Callable[[], float] = time.monotonic):
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.max_seconds = max_seconds
        self.max_cost_usd = max_cost_usd
        self._clock = clock
        self._start = clock()
        self.iterations = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def add_usage(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd

    def tick(self) -> None:
        self.iterations += 1

    def elapsed(self) -> float:
        return self._clock() - self._start

    def exceeded(self) -> str | None:
        """Name of the first limit that was passed, or None."""
        if self.iterations > self.max_iterations:
            return "iterations"
        if self.input_tokens + self.output_tokens > self.max_tokens:
            return "tokens"
        if self.cost_usd > self.max_cost_usd:
            return "cost"
        if self.elapsed() > self.max_seconds:
            return "time"
        return None

    def snapshot(self) -> dict:
        return {
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "seconds": round(self.elapsed(), 1),
        }

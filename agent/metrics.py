"""CloudWatch Embedded Metric Format: a JSON log line becomes a metric, no API call needed."""

import json
import time

NAMESPACE = "AIDevAgent"


def emit(name: str, value: float, unit: str, dims: dict) -> None:
    print(json.dumps({
        "_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [
            {"Namespace": NAMESPACE, "Dimensions": [sorted(dims)], "Metrics": [{"Name": name, "Unit": unit}]}]},
        name: value, **dims,
    }))

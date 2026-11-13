"""Removes secrets and AWS account IDs from any text that leaves the agent."""

import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
]
_ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub("<redacted>", text)
    return _ACCOUNT_ID.sub("<account-id>", text)

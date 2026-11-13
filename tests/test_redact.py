from agent.redact import redact


def test_redact_account_id():
    assert redact("arn:aws:iam::123456789012:role/x") == "arn:aws:iam::<account-id>:role/x"


def test_redact_github_tokens():
    text = "a ghs_abcdefghijklmnopqrstuvwxyz0123456789 b github_pat_11ABCDEFG0abcdefghijklmnop_qrstuv c"
    out = redact(text)
    assert "ghs_" not in out and "github_pat_" not in out
    assert out.count("<redacted>") == 2


def test_redact_private_key_block():
    key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"
    assert redact(f"x {key} y") == "x <redacted> y"


def test_redact_aws_keys():
    assert redact("key AKIAIOSFODNN7EXAMPLE end") == "key <redacted> end"


def test_redact_leaves_normal_text():
    assert redact("order 42 costs 19.90") == "order 42 costs 19.90"

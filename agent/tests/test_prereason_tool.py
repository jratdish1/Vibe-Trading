"""Tests for the read-only PreReason market-context tool."""

from __future__ import annotations

import json

from src.tools.prereason_tool import PreReasonContextTool


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_prereason_tool_is_readonly_and_requires_runtime_key(monkeypatch):
    monkeypatch.delenv("PREREASON_API_KEY", raising=False)

    assert PreReasonContextTool.is_readonly is True
    assert PreReasonContextTool.check_available() is False

    result = json.loads(PreReasonContextTool().execute())
    assert result["status"] == "error"
    assert result["source"] == "prereason"
    assert "not configured" in result["error"]


def test_prereason_context_uses_x_api_key_without_returning_secret(monkeypatch):
    monkeypatch.setenv("PREREASON_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("PREREASON_BASE_URL", "https://api.prereason.com/api")
    captured = {}

    def fake_get(url, *, params, headers, timeout):
        captured.update(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse(
            payload={"signal": "neutral", "confidence": 72},
            headers={"X-RateLimit-Remaining": "59"},
        )

    monkeypatch.setattr("src.tools.prereason_tool.requests.get", fake_get)

    result_text = PreReasonContextTool().execute(
        briefing="macro.snapshot",
        format="json",
    )
    result = json.loads(result_text)

    assert result["status"] == "ok"
    assert result["source"] == "prereason"
    assert result["briefing"] == "macro.snapshot"
    assert result["context"]["signal"] == "neutral"
    assert captured["url"] == "https://api.prereason.com/api/context"
    assert captured["params"] == {"briefing": "macro.snapshot", "format": "json"}
    assert captured["headers"]["X-API-Key"] == "test-secret-not-for-output"
    assert "test-secret-not-for-output" not in result_text


def test_prereason_rate_limit_is_explicit_and_safe(monkeypatch):
    monkeypatch.setenv("PREREASON_API_KEY", "test-secret-not-for-output")

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            status_code=429,
            headers={"Retry-After": "30"},
        )

    monkeypatch.setattr("src.tools.prereason_tool.requests.get", fake_get)

    result_text = PreReasonContextTool().execute(briefing="btc.context")
    result = json.loads(result_text)

    assert result == {
        "status": "rate_limited",
        "source": "prereason",
        "briefing": "btc.context",
        "retry_after": "30",
    }
    assert "test-secret-not-for-output" not in result_text


def test_prereason_rejects_unknown_briefing_before_network(monkeypatch):
    monkeypatch.setenv("PREREASON_API_KEY", "test-secret-not-for-output")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network should not be called for unsupported briefing")

    monkeypatch.setattr("src.tools.prereason_tool.requests.get", fail_if_called)

    result = json.loads(PreReasonContextTool().execute(briefing="unknown.signal"))
    assert result["status"] == "error"
    assert result["error"] == "Unsupported PreReason briefing"

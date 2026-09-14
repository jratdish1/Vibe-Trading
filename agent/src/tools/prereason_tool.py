"""PreReason market-context tool for crypto and macro trading research.

This tool is intentionally read-only. It supplies external market context to the
agent but never places orders, changes positions, or touches wallet/exchange
credentials.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from src.agent.tools import BaseTool


DEFAULT_BASE_URL = "https://api.prereason.com/api"
DEFAULT_TIMEOUT_SECONDS = 10.0

# Current PreReason briefing IDs documented at https://www.prereason.com/docs.
SUPPORTED_BRIEFINGS = {
    "btc.quick-check",
    "btc.context",
    "btc.pulse",
    "btc.grid-stress",
    "macro.snapshot",
    "cross.correlations",
    "btc.momentum",
    "macro.liquidity",
    "btc.on-chain",
    "cross.breadth",
    "btc.miner-survival",
    "btc.etf-flows",
    "btc.full",
    "btc.factors",
    "cross.regime",
    "fx.liquidity",
    "btc.energy",
    "btc.treasury",
}


class PreReasonContextTool(BaseTool):
    """Fetch pre-reasoned market context from PreReason."""

    name = "prereason_context"
    description = (
        "Read-only PreReason market context. When this tool is available, MUST "
        "consult it before forming a crypto/BTC or macro-sensitive trading "
        "recommendation, forecast, strategy assessment, or risk view. Use it as "
        "one corroborating input only; never treat it as authorization to trade. "
        "If PreReason is unavailable or returns an error, say so and continue "
        "with other data rather than fabricating a signal."
    )
    parameters = {
        "type": "object",
        "properties": {
            "briefing": {
                "type": "string",
                "description": (
                    "PreReason briefing ID, e.g. btc.context, macro.snapshot, "
                    "cross.correlations, btc.momentum, or cross.regime"
                ),
                "enum": sorted(SUPPORTED_BRIEFINGS),
                "default": "btc.context",
            },
            "format": {
                "type": "string",
                "description": "Response format from PreReason",
                "enum": ["json", "markdown"],
                "default": "json",
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        """Register only when a PreReason API key is configured."""
        return bool(os.environ.get("PREREASON_API_KEY", "").strip())

    def execute(self, **kwargs: Any) -> str:
        """Fetch one PreReason briefing and return a sanitized result."""
        api_key = os.environ.get("PREREASON_API_KEY", "").strip()
        if not api_key:
            return json.dumps(
                {
                    "status": "error",
                    "source": "prereason",
                    "error": "PREREASON_API_KEY is not configured",
                },
                ensure_ascii=False,
            )

        briefing = str(kwargs.get("briefing", "btc.context")).strip()
        response_format = str(kwargs.get("format", "json")).strip().lower()

        if briefing not in SUPPORTED_BRIEFINGS:
            return json.dumps(
                {
                    "status": "error",
                    "source": "prereason",
                    "error": "Unsupported PreReason briefing",
                    "briefing": briefing,
                },
                ensure_ascii=False,
            )
        if response_format not in {"json", "markdown"}:
            return json.dumps(
                {
                    "status": "error",
                    "source": "prereason",
                    "error": "format must be json or markdown",
                },
                ensure_ascii=False,
            )

        base_url = os.environ.get("PREREASON_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        try:
            timeout = float(os.environ.get("PREREASON_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS

        try:
            response = requests.get(
                f"{base_url}/context",
                params={"briefing": briefing, "format": response_format},
                headers={"X-API-Key": api_key},
                timeout=max(1.0, min(timeout, 30.0)),
            )
        except requests.RequestException as exc:
            return json.dumps(
                {
                    "status": "error",
                    "source": "prereason",
                    "briefing": briefing,
                    "error": f"request_failed: {type(exc).__name__}",
                },
                ensure_ascii=False,
            )

        if response.status_code == 429:
            return json.dumps(
                {
                    "status": "rate_limited",
                    "source": "prereason",
                    "briefing": briefing,
                    "retry_after": response.headers.get("Retry-After"),
                },
                ensure_ascii=False,
            )

        if not response.ok:
            return json.dumps(
                {
                    "status": "error",
                    "source": "prereason",
                    "briefing": briefing,
                    "http_status": response.status_code,
                    "error": "upstream_error",
                },
                ensure_ascii=False,
            )

        if response_format == "markdown":
            payload: Any = response.text
        else:
            try:
                payload = response.json()
            except ValueError:
                return json.dumps(
                    {
                        "status": "error",
                        "source": "prereason",
                        "briefing": briefing,
                        "error": "invalid_json_from_upstream",
                    },
                    ensure_ascii=False,
                )

        return json.dumps(
            {
                "status": "ok",
                "source": "prereason",
                "briefing": briefing,
                "format": response_format,
                "context": payload,
            },
            ensure_ascii=False,
        )

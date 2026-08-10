"""Small, credential-safe OpenAI HTTP client for bounded CauseBase jobs.

The API key is read only from the process environment at request time.  It is
never returned, persisted, or included in raised error text.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.openai.com/v1"


class OpenAIRequestError(RuntimeError):
    """A deliberately sanitised API error suitable for private run metadata."""


@dataclass(frozen=True)
class ApiUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class ApiResult:
    response_id: str | None
    model: str
    status: str | None
    output_text: str
    usage: ApiUsage


def _credential() -> str:
    value = os.environ.get("OPENAI_API_KEY")
    if not value:
        raise OpenAIRequestError("OPENAI_API_KEY is not available to this process")
    return value


def _safe_error(error: HTTPError | URLError) -> str:
    if isinstance(error, HTTPError):
        # Do not include an HTTP body: although it should not contain a secret,
        # it is not needed for the deterministic failure classification.
        return f"OpenAI API request failed with HTTP {error.code}"
    return "OpenAI API request could not connect"


def _post(path: str, payload: dict[str, Any], *, timeout_seconds: int = 60) -> dict[str, Any]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"{API_URL}{path}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {_credential()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as error:
        raise OpenAIRequestError(_safe_error(error)) from None


def _output_text(raw: dict[str, Any]) -> str:
    """Read text from raw Responses API output (the SDK exposes a convenience property)."""
    if raw.get("output_text"):
        return str(raw["output_text"])
    parts: list[str] = []
    for item in raw.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    return "".join(parts)


def responses_create(
    *, model: str, input_text: str, text_format: dict[str, Any], max_output_tokens: int = 1_200,
    max_attempts: int = 2, timeout_seconds: int = 60,
) -> ApiResult:
    """Create one structured response with at most one bounded retry.

    Calls are intentionally serial at this layer. Corpus orchestration controls
    concurrency and cache checks, preventing an accidental retry storm.
    """
    payload = {
        "model": model,
        "input": input_text,
        "max_output_tokens": max_output_tokens,
        "text": {"format": text_format},
    }
    last_error: OpenAIRequestError | None = None
    for attempt in range(max_attempts):
        try:
            raw = _post("/responses", payload, timeout_seconds=timeout_seconds)
            usage = raw.get("usage") or {}
            return ApiResult(
                response_id=raw.get("id"),
                model=raw.get("model", model),
                status=raw.get("status"),
                output_text=_output_text(raw),
                usage=ApiUsage(
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    total_tokens=usage.get("total_tokens"),
                ),
            )
        except OpenAIRequestError as error:
            last_error = error
            if attempt + 1 < max_attempts:
                time.sleep(1 + attempt)
    assert last_error is not None
    raise last_error


def embeddings_create(*, model: str, texts: list[str]) -> tuple[list[list[float]], ApiUsage]:
    if not texts:
        return [], ApiUsage(None, None, None)
    raw = _post("/embeddings", {"model": model, "input": texts})
    rows = sorted(raw.get("data", []), key=lambda row: row["index"])
    usage = raw.get("usage") or {}
    return (
        [row["embedding"] for row in rows],
        ApiUsage(usage.get("prompt_tokens"), None, usage.get("total_tokens")),
    )


def estimate_synthesis_cost(usage: ApiUsage) -> Decimal | None:
    """Current gpt-5-mini non-cached token price, in USD, for run telemetry."""
    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    return (
        Decimal(usage.input_tokens) * Decimal("0.25") / Decimal(1_000_000)
        + Decimal(usage.output_tokens) * Decimal("2.00") / Decimal(1_000_000)
    ).quantize(Decimal("0.000001"))

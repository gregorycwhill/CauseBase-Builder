"""Narrow, auditable OpenAI visual extraction for already selected PDF pages."""
from __future__ import annotations

import base64
import json
import os
from typing import Callable
from urllib.request import Request, urlopen


_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"observations": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["functional_expense_allocation"]},
            "source_label": {"type": "string"}, "share_percent": {"type": "number"},
        }, "required": ["kind", "source_label", "share_percent"],
    }}}, "required": ["observations"],
}

# Snapshot pricing for the default bounded adapter.  The value is an estimate
# from response token usage and is deliberately recorded as such.
_USD_PER_MILLION_TOKENS = {"gpt-5.6-luna": (0.20, 1.20)}


def openai_narrow_vision_extractor(model: str) -> Callable[[dict], dict]:
    """Return a one-page adapter; API credentials are never persisted in output."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI visual extraction")

    def extract(payload: dict) -> dict:
        image = base64.b64encode(payload["image_png"]).decode("ascii")
        request_body = {
            "model": model,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "Extract only functional expense allocations visibly encoded by this single report page. Preserve printed labels exactly. Return no observation unless a percentage is visually associated with its label. Do not infer missing categories or amounts."},
                {"type": "input_image", "image_url": f"data:image/png;base64,{image}", "detail": "high"},
            ]}],
            "text": {"format": {"type": "json_schema", "name": "functional_expense_allocations", "strict": True, "schema": _SCHEMA}},
        }
        request = Request("https://api.openai.com/v1/responses", data=json.dumps(request_body).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        output_text = result.get("output_text") or "".join(part.get("text", "") for item in result.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
        parsed = json.loads(output_text)
        usage = result.get("usage") or {}
        prices = _USD_PER_MILLION_TOKENS.get(model)
        cost = None if not prices else round((usage.get("input_tokens", 0) * prices[0] + usage.get("output_tokens", 0) * prices[1]) / 1_000_000, 8)
        return {"model": model, "usage": usage, "cost": cost, "observations": parsed.get("observations", [])}

    return extract

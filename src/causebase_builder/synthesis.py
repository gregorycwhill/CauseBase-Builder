from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .openai_client import ApiResult, estimate_synthesis_cost, responses_create


SYNTHESIS_PROMPT_VERSION = "phase2a-0.4"
SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "name": "causebase_phase2a_synthesis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "activities": {"type": "array", "items": {"type": "string"}},
            "beneficiaries": {"type": "array", "items": {"type": "string"}},
            "geography": {"type": "array", "items": {"type": "string"}},
            "participation_modes": {"type": "array", "items": {"type": "string"}},
            "taxonomy_term_ids": {"type": "array", "items": {"type": "string"}},
            "uncertainty_note": {"type": "string"},
        },
        "required": [
            "summary", "activities", "beneficiaries", "geography",
            "participation_modes", "taxonomy_term_ids", "uncertainty_note",
        ],
    },
}


def evidence_hash(evidence_pack: dict[str, Any]) -> str:
    canonical = json.dumps(evidence_pack, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def synthesis_prompt(*, evidence_pack: dict[str, Any], taxonomy_terms: list[dict[str, str]]) -> str:
    """Create a compact, evidence-only prompt; callers must not persist it publicly."""
    return """You write a CauseBase Card from the supplied evidence only. Use plain Australian English.

CauseBase is neutral and descriptive: no recommendations, donation encouragement, claims of effectiveness, value judgements, promotional adjectives, or invented detail. Describe concrete activity, beneficiaries, geography and participation where the evidence supports them. Treat organisation-authored claims as claims rather than independent fact. Preserve disagreements and gaps. Do not turn a mission statement into CauseBase voice. Where selected website or report excerpts contain enough concrete information, write a dense 150–220 word summary with multiple grounded details; do not merely compress the evidence into a short abstract. A summary may be shorter only where the selected evidence is genuinely sparse. Never pad a summary with generalities or unsupported detail.

Return the required JSON. Field values must be plain evidence-grounded phrases, not taxonomy labels, evaluative language or inferred outcomes. `taxonomy_term_ids` may contain only supplied IDs and must be a small set (normally no more than eight) of terms directly supported by selected evidence. Do not assign broad terms merely because they might be compatible with an organisation; use an empty list when none is warranted. In particular, regulatory labels such as social welfare, religion, regional/remote, or general charitable purpose do not by themselves establish direct service delivery, general-community beneficiaries, a CauseBase cause term, national reach, or a local operating model. `uncertainty_note` must be empty when there is no material limitation to communicate.

TAXONOMY TERMS:
""" + json.dumps(taxonomy_terms, ensure_ascii=False) + "\n\nEVIDENCE PACK:\n" + json.dumps(evidence_pack, ensure_ascii=False)


def synthesize_evidence(
    *, evidence_pack: dict[str, Any], taxonomy_terms: list[dict[str, str]], model: str = "gpt-5-mini",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one bounded structured synthesis and return public-safe provenance."""
    packed_hash = evidence_hash(evidence_pack)
    result: ApiResult = responses_create(
        model=model,
        input_text=synthesis_prompt(evidence_pack=evidence_pack, taxonomy_terms=taxonomy_terms),
        text_format=SYNTHESIS_SCHEMA,
        max_output_tokens=3_000,
    )
    if result.status not in {"completed", None}:
        raise ValueError(f"synthesis did not complete (status: {result.status})")
    try:
        payload = json.loads(result.output_text)
    except json.JSONDecodeError as error:
        raise ValueError("synthesis response was not valid structured JSON") from error
    return payload, {
        "model_id": result.model,
        "prompt_version": SYNTHESIS_PROMPT_VERSION,
        "parameters": {"max_output_tokens": 3000, "structured_output": True},
        "evidence_input_hash": packed_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "editorial_policy_version": "0.1",
        "request_id": result.response_id,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "estimated_cost_usd": str(estimate_synthesis_cost(result.usage)) if estimate_synthesis_cost(result.usage) is not None else None,
    }


def deterministic_fixture_summary(source: dict) -> str:
    """Credential-free fixture synthesiser.

    Production synthesis will be provider-backed and governed by EDITORIAL_POLICY.md.
    This function deliberately creates plain, prosaic copy from structured evidence.
    """
    activities = source.get("activities", [])
    beneficiaries = source.get("beneficiaries", [])
    geography = source.get("geography", [])
    participation = source.get("participation_modes", [])

    activity_text = ", ".join(activities[:-1])
    if len(activities) > 1:
        activity_text += f" and {activities[-1]}"
    elif activities:
        activity_text = activities[0]
    else:
        activity_text = "undertakes charitable activities"

    geo_text = "; ".join(geography) if geography else "Australia"
    beneficiary_text = ", ".join(beneficiaries) if beneficiaries else "its target communities"

    sentence = (
        f"{source['display_name']} {activity_text} in {geo_text}, "
        f"serving {beneficiary_text}."
    )
    if participation:
        sentence += " Public participation includes " + ", ".join(participation) + "."
    return sentence

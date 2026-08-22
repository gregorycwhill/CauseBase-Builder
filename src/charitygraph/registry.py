"""Governed durable CauseBase subject-identity registry."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event_type: str, **details: object) -> dict:
    return {"event_type": event_type, "at": _now(), **details}


def _valid_abn(value: str) -> str | None:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 11:
        return None
    weighted = (int(digits[0]) - 1) * 10 + sum(
        int(digit) * weight for digit, weight in zip(digits[1:], (1, 3, 5, 7, 9, 11, 13, 15, 17, 19), strict=True)
    )
    return digits if weighted % 89 == 0 else None


class SubjectRegistry:
    def __init__(self, path: Path, payload: dict | None = None):
        self.path = path
        self.payload = payload or {"registry_version": "0.1", "subjects": []}

    @classmethod
    def load(cls, path: Path) -> "SubjectRegistry":
        return cls(path, json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)

    @property
    def subjects(self) -> list[dict]:
        return self.payload["subjects"]

    def get(self, causebase_id: str) -> dict:
        for subject in self.subjects:
            if subject["causebase_id"] == causebase_id:
                return subject
        raise KeyError(causebase_id)

    def mint(
        self, *, display_name: str, subject_kind: str, resolution_status: str,
        resolution_basis: str, source_record_ids: list[str], promotion_method: str = "reviewed_manual"
    ) -> dict:
        if resolution_status != "resolved":
            raise ValueError("only resolved subjects may be promoted")
        causebase_id = f"cb_{uuid.uuid4().hex}"
        while any(s["causebase_id"] == causebase_id for s in self.subjects):
            causebase_id = f"cb_{uuid.uuid4().hex}"
        created_at = _now()
        subject = {
            "causebase_id": causebase_id,
            "created_at": created_at,
            "first_public_release": None,
            "identity_lifecycle_status": "current",
            "subject_kind": subject_kind,
            "current_display_name": display_name,
            "successor_ids": [],
            "predecessor_ids": [],
            "promotion": {
                "resolution_status": resolution_status,
                "resolution_basis": resolution_basis,
                "source_record_ids": source_record_ids,
                "promotion_method": promotion_method,
            },
            "lifecycle_events": [_event("SUBJECT_CREATED", promotion_method=promotion_method)],
        }
        self.subjects.append(subject)
        return subject

    def promote_authoritative_acnc(
        self, *, source_record_id: str, abn: str, legal_name: str, source_id: str,
        source_version: str, evidence_ids: list[str], display_name: str | None = None,
        policy_version: str = "acnc-authoritative-v1",
    ) -> dict:
        """Mint a Phase 2A subject without resolving its ontology.

        An ACNC record establishes an independently addressable registered
        subject, not a canonical public organisation, brand, group, or legal
        person. Federation is therefore not an automatic exclusion.
        """
        digits = _valid_abn(abn)
        if digits is None:
            raise ValueError("ACNC automated promotion requires a valid ABN")
        if not source_record_id or not legal_name.strip() or not source_id or not source_version:
            raise ValueError("ACNC automated promotion requires source record, source/version and legal name")
        for subject in self.subjects:
            promotion = subject.get("promotion", {})
            if source_record_id in promotion.get("source_record_ids", []):
                raise ValueError(f"source record already governedly bound: {source_record_id}")
            if digits in promotion.get("external_identifiers", {}).get("abn", []):
                raise ValueError(f"ABN already governedly bound: {digits}")
        subject = self.mint(
            display_name=display_name or legal_name,
            subject_kind="unknown",
            resolution_status="resolved",
            resolution_basis="authoritative current ACNC Register record with valid ABN under constrained promotion policy",
            source_record_ids=[source_record_id],
            promotion_method="automated_authoritative_source",
        )
        subject["promotion"].update({
            "promotion_method": "automated_authoritative_source",
            "promotion_policy": policy_version,
            "source_record_ids": [source_record_id],
            "external_identifiers": {"abn": [digits]},
            "source_id": source_id,
            "source_version": source_version,
            "registered_legal_name_at_promotion": legal_name,
            "evidence_ids": list(evidence_ids),
            "initial_subject_kind": "unknown",
        })
        subject["lifecycle_events"].append(_event(
            "SUBJECT_PROMOTED_AUTOMATICALLY",
            promotion_policy=policy_version,
            source_record_id=source_record_id,
            abn=digits,
        ))
        return subject

    def merge(self, *, survivor_id: str, loser_id: str, effective_release: str | None = None) -> None:
        survivor, loser = self.get(survivor_id), self.get(loser_id)
        if survivor_id == loser_id or loser["identity_lifecycle_status"] != "current":
            raise ValueError("merge requires distinct current subjects")
        loser["identity_lifecycle_status"] = "merged"
        loser["successor_ids"] = [survivor_id]
        loser["lifecycle_events"].append(_event("SUBJECT_MERGED", successor_id=survivor_id, effective_release=effective_release))
        survivor["predecessor_ids"] = sorted(set(survivor["predecessor_ids"] + [loser_id]))
        survivor["lifecycle_events"].append(_event("SUBJECT_MERGED_IN", predecessor_id=loser_id, effective_release=effective_release))

    def split(self, *, original_id: str, successors: list[dict], effective_release: str | None = None) -> list[dict]:
        original = self.get(original_id)
        if original["identity_lifecycle_status"] != "current":
            raise ValueError("only a current subject may split")
        created = [self.mint(**successor) for successor in successors]
        original["identity_lifecycle_status"] = "split"
        original["successor_ids"] = [subject["causebase_id"] for subject in created]
        original["lifecycle_events"].append(_event("SUBJECT_SPLIT", successor_ids=original["successor_ids"], effective_release=effective_release))
        for subject in created:
            subject["predecessor_ids"] = [original_id]
        return created

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.payload, indent=2), encoding="utf-8")

    def validate_card_bindings(self, cards) -> list[str]:
        """Real publication cards must bind to governed current identities."""
        errors = []
        for card in cards:
            try:
                subject = self.get(card.causebase_id)
            except KeyError:
                errors.append(f"{card.causebase_id}: absent from durable subject registry")
                continue
            if subject["identity_lifecycle_status"] != "current":
                errors.append(
                    f"{card.causebase_id}: cannot publish active card for {subject['identity_lifecycle_status']} identity"
                )
        return errors

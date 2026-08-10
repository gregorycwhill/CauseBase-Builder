from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import CauseBaseCard
from .render import file_sha256


FORBIDDEN_PUBLIC_SUFFIXES = {".pdf", ".warc", ".sqlite", ".db", ".env"}
FORBIDDEN_PUBLIC_NAMES = {".env", "api_key.txt", "secrets.json"}


def is_allowed_public_path(relative_path: str) -> bool:
    """Allow only explicitly rendered public artefacts in the provisional fixture release."""
    if relative_path in {
        "causebase.json",
        "causebase.jsonl",
        "causebase.csv",
        "causebase.parquet",
        "embeddings.json",
        "embeddings.parquet",
        "similarities.json",
        "similarities.parquet",
        "manifest.json",
        "schema/card.schema.json",
        "taxonomy/causebase-v0.json",
        "coverage.json",
        "agent-guide.md",
    }:
        return True
    parts = relative_path.split("/")
    return len(parts) == 2 and parts[0] == "cards" and (parts[1].endswith(".md") or parts[1].endswith(".json"))


def validate_card(card: CauseBaseCard) -> list[str]:
    errors = []
    if not card.causebase_id.strip():
        errors.append("blank CauseBase subject ID")
    capabilities = [observation.capability for observation in card.coverage]
    if len(capabilities) != len(set(capabilities)):
        errors.append(f"{card.causebase_id}: duplicate effective coverage capability")
    if card.enrichment_level in {"enriched", "rich"}:
        if card.fundraising_expenditure and card.fundraising_expenditure.normalised_amount is None:
            errors.append(f"{card.causebase_id}: blank fundraising expenditure")
        if card.fundraising_expenditure and not card.fundraising_expenditure.method:
            errors.append(f"{card.causebase_id}: fundraising method missing")
    for c in card.classifications:
        if not c.taxonomy_id or not c.taxonomy_version or not c.term_id:
            errors.append(f"{card.causebase_id}: invalid classification")
        missing = set(c.evidence_ids) - {e.evidence_id for e in card.evidence}
        if missing:
            errors.append(
                f"{card.causebase_id}: classification evidence IDs missing: {sorted(missing)}"
            )
    evidence_ids = {e.evidence_id for e in card.evidence}
    for observation in card.coverage:
        missing = set(observation.evidence_ids) - evidence_ids
        if missing:
            errors.append(f"{card.causebase_id}: coverage evidence IDs missing: {sorted(missing)}")
    for registration in card.registrations:
        missing = set(registration.evidence_ids) - evidence_ids
        if missing:
            errors.append(f"{card.causebase_id}: registration evidence IDs missing: {sorted(missing)}")
    for tax_status in card.tax_statuses:
        missing = set(tax_status.evidence_ids) - evidence_ids
        if missing:
            errors.append(f"{card.causebase_id}: tax-status evidence IDs missing: {sorted(missing)}")
    lower = card.causebase_summary.lower()
    for phrase in ["recommended for you", "best charity", "you should donate"]:
        if phrase in lower:
            errors.append(f"{card.causebase_id}: recommendation language in summary")
    if card.synthesis and set(card.synthesis.model_dump()) & {
        "request_id", "input_tokens", "output_tokens", "estimated_cost_usd"
    }:
        errors.append(f"{card.causebase_id}: public operational synthesis telemetry")
    return errors


def validate_publication(output_dir: Path) -> list[str]:
    errors = []

    required = {
        "causebase.json",
        "causebase.jsonl",
        "causebase.csv",
        "embeddings.json",
        "similarities.json",
        "manifest.json",
        "schema/card.schema.json",
    }
    actual = {
        str(p.relative_to(output_dir)).replace("\\", "/")
        for p in output_dir.rglob("*")
        if p.is_file()
    }
    for rel in sorted(required - actual):
        errors.append(f"missing required artefact: {rel}")

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        relative_path = str(path.relative_to(output_dir)).replace("\\", "/")
        if path.name in FORBIDDEN_PUBLIC_NAMES or path.suffix.lower() in FORBIDDEN_PUBLIC_SUFFIXES:
            errors.append(f"forbidden publication artefact: {path.relative_to(output_dir)}")
        elif not is_allowed_public_path(relative_path):
            errors.append(f"unexpected publication artefact: {relative_path}")

    data_path = output_dir / "causebase.json"
    if data_path.exists():
        rows = json.loads(data_path.read_text(encoding="utf-8"))["entities"]
        cards = [CauseBaseCard.model_validate(row) for row in rows]
        ids = [card.causebase_id for card in cards]
        duplicate_ids = sorted({causebase_id for causebase_id in ids if ids.count(causebase_id) > 1})
        if duplicate_ids:
            errors.append(f"duplicate CauseBase subject IDs: {duplicate_ids}")
        financial_owners: dict[str, list[str]] = {}
        for card in cards:
            for financial_record in card.financial_records:
                financial_owners.setdefault(financial_record.financial_record_id, []).append(
                    card.causebase_id
                )
        duplicated_financials = {
            financial_record_id: owners
            for financial_record_id, owners in financial_owners.items()
            if len(owners) > 1
        }
        if duplicated_financials:
            errors.append(
                "financial record duplicated across public cards: "
                f"{duplicated_financials}"
            )
        for card in cards:
            errors.extend(validate_card(card))

        csv_path = output_dir / "causebase.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as f:
                csv_rows = {row["causebase_id"]: row for row in csv.DictReader(f)}
            for card in cards:
                row = csv_rows.get(card.causebase_id)
                if not row:
                    errors.append(f"{card.causebase_id}: missing from CSV projection")
                    continue
                if card.fundraising_expenditure and abs(float(row["fundraising_expenditure"]) - float(card.fundraising_expenditure.normalised_amount)) > 0.001:
                    errors.append(f"{card.causebase_id}: fundraising mismatch JSON vs CSV")
                if card.fundraising_expenditure is None and row["fundraising_expenditure"]:
                    errors.append(f"{card.causebase_id}: unexpected CSV fundraising value")

        for card in cards:
            from .render import card_locator

            md_path = output_dir / card_locator(card)
            if not md_path.exists():
                errors.append(f"{card.causebase_id}: Markdown card missing")
            else:
                md = md_path.read_text(encoding="utf-8")
                if card.fundraising_expenditure and str(card.fundraising_expenditure.normalised_amount) not in md:
                    errors.append(f"{card.causebase_id}: Markdown fundraising value mismatch")
                if "[0." in md or "[-0." in md:
                    errors.append(f"{card.causebase_id}: raw embedding vector appears in Markdown")
            from .render import card_json_locator
            if not (output_dir / card_json_locator(card)).exists():
                errors.append(f"{card.causebase_id}: JSON card missing")

    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative_path, metadata in manifest.get("artefacts", {}).items():
            path = output_dir / relative_path
            if not path.exists():
                errors.append(f"manifest artefact missing: {relative_path}")
            elif metadata.get("bytes") != path.stat().st_size:
                errors.append(f"manifest artefact size mismatch: {relative_path}")
            elif metadata.get("sha256") != file_sha256(path):
                errors.append(f"manifest artefact hash mismatch: {relative_path}")

    return errors


def mark_manifest_validated(output_dir: Path, errors: list[str]) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation"] = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

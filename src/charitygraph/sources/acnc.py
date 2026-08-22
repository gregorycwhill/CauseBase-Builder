"""Minimal ACNC Register CSV adapter for the bounded reality spike.

The adapter deliberately normalises source records without asserting that an ACNC
record is the universal CauseBase subject. Entity resolution and relationships are
separate steps.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..models import ExternalIdentifier


CAUSEBASE_PROVISIONAL_NAMESPACE = uuid.UUID("2c35f0aa-d723-4a59-bbe5-78610c6bf0f7")


def _normalise_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _value(row: dict[str, str], *aliases: str) -> str | None:
    normalised = {_normalise_header(key): value.strip() for key, value in row.items() if value}
    for alias in aliases:
        value = normalised.get(_normalise_header(alias))
        if value:
            return value
    return None


def source_record_id(seed: str) -> str:
    """Stable source-record identity, deliberately distinct from any CauseBase subject."""
    return f"src:acnc-register:{uuid.uuid5(CAUSEBASE_PROVISIONAL_NAMESPACE, seed)}"


@dataclass(frozen=True)
class AcncRegisterRecord:
    source_record_id: str
    legal_name: str
    display_name: str
    status: str | None
    external_identifiers: tuple[ExternalIdentifier, ...]
    raw: dict[str, str]


def parse_acnc_register_csv(path: Path) -> list[AcncRegisterRecord]:
    """Parse a downloaded ACNC Register CSV using common header aliases.

    It retains source columns for spike analysis and emits no public card. Each
    record needs an ACNC registration ID or ABN; records without either are a
    source-quality failure rather than an invented identity.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    records: list[AcncRegisterRecord] = []
    for row in rows:
        acnc_id = _value(row, "ACNC Registration Number", "ACNC ID", "Charity Registration Number")
        abn = _value(row, "ABN", "Australian Business Number")
        legal_name = _value(row, "Charity Legal Name", "Legal Name", "Charity Name")
        display_name = _value(row, "Charity Name", "Trading Name", "Charity Legal Name")
        if not legal_name or not display_name:
            # Malformed rows remain a source-quality issue; do not manufacture a
            # record from a name alone during an identifier-based Register import.
            continue
        if not acnc_id and not abn:
            continue

        identifiers = []
        if acnc_id:
            identifiers.append(ExternalIdentifier(scheme="acnc_registration_id", value=acnc_id))
        if abn:
            identifiers.append(ExternalIdentifier(scheme="abn", value=abn))
        seed = f"acnc:{acnc_id}" if acnc_id else f"abn:{abn}"
        records.append(
            AcncRegisterRecord(
                source_record_id=source_record_id(seed),
                legal_name=legal_name,
                display_name=display_name,
                status=_value(row, "Charity Status", "Status", "Registration Status"),
                external_identifiers=tuple(identifiers),
                raw=dict(row),
            )
        )
    return records

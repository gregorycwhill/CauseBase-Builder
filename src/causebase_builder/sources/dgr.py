"""Minimal ABR/DGR CSV adapter for reality-spike authoritative status evidence."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .acnc import _value


@dataclass(frozen=True)
class DgrRecord:
    abn: str
    dgr_status: str | None
    dgr_item: str | None
    raw: dict[str, str]


def iter_dgr_bulk_extract(zip_paths: list[Path]):
    """Stream ABR bulk XML and yield only dated DGR observations.

    The ABR archive contains national ABN records; this iterator deliberately
    discards non-DGR records and never treats DGR status as identity.
    """
    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            for entry in archive.infolist():
                if not entry.filename.lower().endswith(".xml"):
                    continue
                with archive.open(entry) as stream:
                    for _, element in ET.iterparse(stream, events=("end",)):
                        if element.tag != "ABR":
                            continue
                        abn_node = element.find("ABN")
                        dgr_nodes = [node for node in element.iter() if "dgr" in node.tag.lower() or "deductiblegift" in node.tag.lower()]
                        if abn_node is not None and dgr_nodes:
                            yield DgrRecord(
                                abn=(abn_node.text or "").strip(),
                                dgr_status="endorsed",
                                dgr_item=None,
                                raw={"bulk_entry": entry.filename, "dgr_node_count": str(len(dgr_nodes))},
                            )
                        element.clear()


def parse_dgr_csv(path: Path) -> list[DgrRecord]:
    """Extract DGR fields from a permitted ABR/other authoritative CSV export."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records = []
    for row in rows:
        abn = _value(row, "ABN", "Australian Business Number")
        if not abn:
            raise ValueError("DGR row missing ABN")
        records.append(
            DgrRecord(
                abn=abn,
                dgr_status=_value(row, "DGR Status", "Deductible Gift Recipient Status"),
                dgr_item=_value(row, "DGR Item", "Deductible Gift Recipient Item"),
                raw=dict(row),
            )
        )
    return records

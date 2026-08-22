import json
from pathlib import Path

from charitygraph.config import load_paths


INVENTORY = load_paths(Path(__file__).resolve().parents[2]).data_repository_root / "golden" / "document-extraction-ecosystem-v1.json"

def test_ecosystem_inventory_is_complete_and_has_explicit_screening():
    inventory=json.loads(INVENTORY.read_text()); candidates=inventory["candidates"]
    assert 8 <= len(candidates) <= 15
    required={"name","version","family","licence","python_api","windows","private_local","capabilities","disposition"}
    assert all(required <= set(candidate) and candidate["disposition"] for candidate in candidates)
    assert "popularity is a quality score" not in inventory["selection_principle"].casefold()
    assert {"shortlist_primary","shortlist_specialist","shortlist_ocr"} <= {candidate["disposition"] for candidate in candidates}

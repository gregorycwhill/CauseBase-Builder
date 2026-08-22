import json
from pathlib import Path

from charitygraph.config import load_paths
from charitygraph.v05.models import CapabilityRegistry, ReleaseContext
from charitygraph.v05.release import assemble_release


DATA = load_paths(Path(__file__).resolve().parents[2]).data_repository_root


def test_release_assembly_has_complete_manifest_and_lossless_audit(tmp_path):
    registry = CapabilityRegistry.model_validate(json.loads((DATA / "examples/vnext/capability-registry.json").read_text(encoding="utf-8")))
    context = ReleaseContext(release_id="v05-test-release", dataset_version="0.5.0-test", based_on_release="rc4-2026-08-14", generated_at="2026-08-15T00:00:00Z", capability_registry={"registry_id": registry.registry_id, "path": "capability-registry.json"})
    manifest = assemble_release(DATA / "releases/rc4-2026-08-14", tmp_path, registry, context)
    assert manifest["validation"]["status"] == "passed"
    assert manifest["entity_count"] == 120 and manifest["source_record_count"] == 228
    assert len(list((tmp_path / "cards").glob("*.json"))) == 120
    assert len(list((tmp_path / "source-records").glob("*.json"))) == 228

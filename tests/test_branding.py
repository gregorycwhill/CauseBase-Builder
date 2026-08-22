from __future__ import annotations

import subprocess
import sys
import warnings
import os
from pathlib import Path

from charitygraph.config import load_paths


ROOT = Path(__file__).parents[1]


def test_charitygraph_package_and_canonical_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARITYGRAPH_RUNTIME_ROOT", str(tmp_path / "runtime"))
    paths = load_paths(tmp_path)
    assert paths.runtime_root == tmp_path / "runtime"
    assert paths.data_repository_root == tmp_path / "charitygraph-data"


def test_legacy_environment_variable_warns(monkeypatch, tmp_path):
    monkeypatch.delenv("CHARITYGRAPH_RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("CAUSEBASE_RUNTIME_ROOT", str(tmp_path / "legacy-runtime"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert load_paths(tmp_path).runtime_root == tmp_path / "legacy-runtime"
    assert any("deprecated" in str(item.message) for item in caught)


def test_brand_lint_and_cli_smoke():
    result = subprocess.run([sys.executable, "scripts/brand_lint.py"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    help_result = subprocess.run([sys.executable, "-m", "charitygraph", "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert help_result.returncode == 0
    assert "usage: charitygraph" in help_result.stdout

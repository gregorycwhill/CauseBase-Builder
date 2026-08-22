"""Explicit coverage for the temporary pre-CharityGraph compatibility surface."""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings
from pathlib import Path


def test_legacy_package_import_warns_and_resolves_canonical_module():
    sys.modules.pop("causebase_builder", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy = importlib.import_module("causebase_builder")
    canonical = importlib.import_module("charitygraph")

    assert legacy.__path__ == canonical.__path__
    assert any("deprecated" in str(item.message) for item in caught)


def test_legacy_cli_alias_warns_and_delegates_to_charitygraph():
    legacy_cli = Path(sys.executable).with_name("causebase.exe")
    result = subprocess.run([legacy_cli, "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "usage: charitygraph" in result.stdout
    assert "deprecated" in result.stderr.lower()

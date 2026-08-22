# Builder test baseline before rearchitecture

**Status:** Restored after the CharityGraph public cutover
**Scope:** Builder test and operational-path repair only; no Part 2 rearchitecture

## Environment and commands

The documented `uv sync --extra dev` setup was unavailable on the test host
because `uv` was not installed. An isolated temporary virtual environment was
created with `python -m venv`, followed by `python -m pip install -e '.[dev]'`.
It used Python 3.13.7, Pydantic 2.13.4, pandas 2.3.3, pyarrow 21.0.0 and pytest
9.1.1.

Run the full suite with:

```powershell
<isolated-python> -m pytest -q
```

The public Data dependency is resolved from `CHARITYGRAPH_DATA_REPOSITORY` or,
by default, the sibling `charitygraph-data` repository. It is public checked-in
test material, not a private archive or developer-specific absolute path.

## Original baseline

Two clean runs collected 117 tests and each produced 101 passed / 16 failed.
There were no skipped or errored tests. The failures were deterministic:

- **A — rebrand residue (11):** `test_document_ecosystem_inventory`, both
  `test_golden_corpus` tests, `test_cached_phase2a_synthesis`, all six
  `test_v05_fixture_adapter` tests, and `test_v05_release` hard-coded the
  retired `CauseBase-Data` sibling directory or compatibility package path.
- **B — obsolete test expectation (1):**
  `test_diagnostics_are_deterministic_and_not_a_taxonomy_mutation` constructed
  a `causebase` classification even though the frozen checked-in taxonomy is
  `charitygraph` version `0.1-phase2a`.
- **C — current production defect (4):** all four `test_taxonomy_workflow`
  tests exposed workflow code that rejected the checked-in frozen
  `charitygraph` taxonomy and hard-coded the retired taxonomy ID while finding
  representative cases and validation impact.

There were no environment/fixture defects or unresolved architectural
ambiguities.

## Repairs

- Test access to public Data now uses the configured `CharityGraphPaths`
  location rather than an old workspace-directory spelling.
- Ordinary Builder tests use the canonical `charitygraph` import namespace.
  `test_legacy_compatibility.py` explicitly retains coverage of the warning-
  emitting `causebase_builder` import and `causebase` CLI alias.
- The frozen taxonomy workflow now requires `charitygraph` `0.1-phase2a` and
  consistently uses the loaded taxonomy ID instead of a hard-coded retired ID.
- Taxonomy workflow documentation and development examples use canonical
  `charitygraph` commands. Historical compatibility identifiers remain intact.

## Result

The final suite collects and passes 119 tests with no skips, errors or expected
failures. The focused regression suite remains 12 passing tests. Package,
canonical CLI, legacy import/CLI warning and brand-lint checks are run as part
of the release validation for this repair.

The immutable Data manifest was not modified. Its required SHA-256 is:

```text
01D047484909B8E15941D5023749ECDB6811FA472CB04BD1B9E0272935050DFB
```

## Retained compatibility identifiers

`causebase_id`, `taxonomy.causebase`, immutable v0.5 metadata and artefact
names, the `causebase_builder` import shim, legacy `causebase` CLI, and
`CAUSEBASE_*` environment-variable aliases remain intentionally supported
where documented. They are not new production naming conventions.

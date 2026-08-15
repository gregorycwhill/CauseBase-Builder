# CauseBase Builder

**Status:** Canonical repository overview  
**Version:** 0.1

CauseBase Builder is the local production engine for CauseBase.

It acquires public source material, converts it into structured evidence, derives and estimates fields, synthesises CauseBase Cards, assigns classifications, creates semantic representations, validates the complete publication candidate, and emits the public artefacts consumed by CauseBase Data and CauseBase Viewer.

Builder is not the public website and is not the canonical public dataset. It is the reproducible method by which CauseBase Data is manufactured. Builder implements the shared CauseBase product contract; CauseBase Data is a sibling sub-product, not Builder's parent.

## Core responsibilities

Builder is responsible for:

1. source discovery and acquisition;
2. source snapshotting and change detection;
3. PDF, HTML, table and structured-data extraction;
4. evidence normalisation and provenance;
5. mechanical derivation of facts and metrics;
6. required estimates, including fundraising expenditure;
7. LLM-assisted interpretation and card synthesis;
8. multi-taxonomy classification;
9. embeddings and derived similarity data;
10. community correction inputs;
11. validation and publication gating;
12. rendering publication-ready data and cards;
13. release manifests and reproducibility metadata.

## Non-responsibilities

Builder does not:

- recommend charities;
- rank charities by desirability;
- process donations;
- run the public Viewer;
- own user identity or accounts;
- directly mutate a live public database;
- publish raw annual reports, scraped websites or other third-party source archives merely because they were used during processing.

## Local operating model

The intended development loop is:

`VS Code + Codex -> local Python -> tests/build output -> Codex`

The intended production loop is:

`Windows Task Scheduler -> CauseBase Builder -> validate -> stage -> publish -> verify -> log/alert`

The full national source and working corpus remains local. Public publication artefacts are deliberately separated from working data.

## Physical separation

A recommended local layout is:

```text
OneDrive durable archive\
  CauseBase\archive\
    sources\
    processed\
    governed-inputs\
Local mutable runtime\
  CauseBase-runtime\
    state\ temp\ cache\ logs\ staging\
OneDrive repositories\
  CauseBase\
    CauseBase-Builder\ CauseBase-Data\ CauseBase-Viewer\
```

Archive, runtime and publication paths are configurable. Raw source material never becomes Git content merely because storage is OneDrive-backed.

## Canonical documents

- `ARCHITECTURE.md` — pipeline, local storage and stage boundaries
- `CARD_SPEC.md` — canonical CauseBase entity/card contract
- `PROVENANCE_AND_ESTIMATION.md` — evidence, confidence and required-estimate rules
- `TAXONOMIES.md` — multi-taxonomy model
- `EDITORIAL_POLICY.md` — house style and LLM synthesis rules
- `CORRECTIONS.md` — public correction inputs and patch semantics
- `BUILD_AND_PUBLICATION.md` — validation, staging, release and publication contract
- `AGENTS.md` — instructions for coding agents working in this repository

High-level CauseBase product documents remain authoritative where these implementation documents conflict with them.
Their canonical GitHub-visible copies are in [CauseBase-Data](https://github.com/gregorycwhill/CauseBase-Data): `CURRENT_STATE.md`, `ROADMAP.md`, `IMPLEMENTATION_PLAN.md`, `TEST_PLAN.md` and `CODEX_TO_CHATGPT_HANDOFF.md`.

## Public contract 0.5 fixture implementation

The legacy RC4 models and publisher remain the production path. The isolated
`causebase_builder.v05` package contains the approved v0.5 fixture work:

- `v05.models` â€” public Pydantic models and exact decimal-string money types;
- `v05.adapter.adapt_rc4_fixture` â€” deterministic, injected-context RC4 fixture adapter;
- `v05.validate.validate_v05_card` and `validate_v05_fixture_release` â€” independent v0.5 validation.

Run `python -m pytest tests/test_v05_fixture_adapter.py` for the frozen
four-fixture conformance suite. It does not migrate the 120-card corpus or
alter the RC4 publication path.

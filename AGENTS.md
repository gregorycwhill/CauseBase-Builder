# CharityGraph — Agent Instructions

> The former CauseBase name is retained only for documented legacy compatibility and immutable release material. Current package, CLI, environment, output, and repository names use CharityGraph.

**Status:** Canonical repository instructions  
**Version:** 0.1

These rules apply to coding agents working on CharityGraph.

## Shared CharityGraph project memory

The canonical shared state and planning documents live in the sibling
[`charitygraph-data`](https://github.com/gregorycwhill/charitygraph-data) repository:

- `CURRENT_STATE.md`
- `ROADMAP.md`
- `IMPLEMENTATION_PLAN.md`
- `TEST_PLAN.md`
- `CODEX_TO_CHATGPT_HANDOFF.md`

Read those files before changing cross-product contracts. Do not create or maintain workspace-root duplicates.

## Product boundary

CharityGraph Builder produces open, inspectable charity data. It does not implement recommendation, ranking, persuasion, donation allocation or behavioural nudging.

Do not add recommendation logic without an explicit product decision changing that boundary.

## Working-data safety

- Raw sources and processed working data are local working artefacts, not repository content.
- Never add annual-report PDFs, scraped HTML, complete source datasets, LLM request dumps or similar source archives to Git.
- Do not rely only on `.gitignore` as the publication boundary.
- Publication code must use an explicit allowlist of permitted artefacts.
- Never use `git add -A` as part of publication automation.

## Model-context discipline

- Do not load complete national datasets or large document corpora into agent context.
- Use Python over the full data.
- Inspect representative samples, aggregate diagnostics, failures and targeted records.
- Prefer deterministic preprocessing before LLM interpretation.
- Test changes on small fixtures before running expensive or national-scale stages.

## Generated outputs

- Do not manually edit generated publication files.
- Change source evidence, rules, corrections, taxonomy data or code and regenerate.
- JSON, CSV, Parquet and Markdown representations must derive from the same canonical entity/card representation.
- A mismatch between published representations is a build failure.
- Current public identity, card and evidence schemas are provisional until the real-data reality spike is reviewed. Do not freeze or expand them from synthetic fixtures alone.
- Use opaque legacy CauseBase subject IDs. ABN, ACNC ID and other source identifiers are external identifiers, not universal primary keys.

## Evidence and provenance

Every material derived assertion should preserve its derivation path where practicable.

Distinguish:

- regulatory/authoritative fact;
- organisation self-report;
- independent source;
- community contribution;
- deterministic derivation;
- heuristic estimate;
- LLM interpretation;
- statistical imputation.

Do not silently promote an estimate or interpretation into a measured fact.

## Fundraising expenditure

Fundraising expenditure may be unavailable/null when selected evidence does not support a defensible value. Persist an explicit coverage observation explaining the unavailability.

Use only direct disclosure, deterministic reconstruction, or a documented bounded interpretation. Universal priors and peer-imputation fill are prohibited for fundraising expenditure; never force a midpoint or point estimate. Every published value must include method and provenance.

## LLM usage

- LLMs interpret selected evidence; they are not the default web crawler or PDF parser.
- Strip boilerplate and irrelevant content mechanically first.
- Use the lowest-cost model that meets the quality requirement.
- Escalate difficult or high-risk cases rather than routing the entire corpus to a frontier model.
- Structured outputs must validate against the relevant schema.
- Follow `EDITORIAL_POLICY.md`.
- Preserve uncertainty and source references.
- Never allow promotional source wording to become CharityGraph voice by default.

## Taxonomies

- Multi-taxonomy support is foundational.
- Never hard-code an assumption that CharityGraph taxonomy is the only or canonical worldview.
- Every classification identifies taxonomy and version.
- Use stable term IDs.
- Do not invent taxonomy terms at inference time.
- Crosswalks may be approximate; preserve mapping relationship and provenance.
- Design and test CharityGraph taxonomy v0 during the reality spike; it must be usable for enriched-card classification and Viewer filtering before large-scale synthesis.

## Corrections

- Public corrections are governed inputs, not direct mutations of generated output.
- Accepted corrections should alter evidence/overrides before dependent synthesis where possible.
- Regenerate dependent summary, classifications, embeddings and similarities after relevant corrections.
- Preserve correction status/history according to `CORRECTIONS.md`.
- Keep raw intake private. Public contestability uses moderated, governed proposal/decision records.

## Testing expectations

At minimum test:

- parsing and normalisation;
- ABN validity and entity identity;
- source contracts;
- financial calculations;
- fundraising-estimation policy and unavailable-value handling;
- taxonomy term validity;
- canonical card schema;
- representation consistency;
- embedding model/dimension/version metadata;
- provenance resolvability;
- publication allowlist;
- publication manifests;
- representative editorial-policy examples;
- drift and anomaly thresholds.

A program that exits successfully but produces implausible data has failed.

## Preferred implementation character

Prefer:

- clear Python modules;
- small explicit interfaces;
- standard file formats;
- deterministic steps;
- content hashes;
- inspectable state;
- simple command-line orchestration;
- local reproducibility;
- boring dependencies.

Avoid infrastructure introduced solely because it is fashionable.

## Before declaring work complete

1. Run the relevant unit/integration tests.
2. Run a representative fixture build.
3. Inspect generated diagnostics.
4. Confirm no private/source artefacts entered the publication tree.
5. Confirm public representations agree.
6. Report what changed, tests run, known limitations and whether a full production rebuild is still required.

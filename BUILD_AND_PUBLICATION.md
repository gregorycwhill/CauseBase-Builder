# CauseBase Build and Publication Contract

**Status:** Canonical operational contract  
**Version:** 0.1

## 1. Principle

Building and publishing are separate operations.

A successful processing run does not automatically imply its outputs are safe or valid to publish.

## 2. Publication candidate

Builder creates a complete release candidate in a dedicated staging location.

Only publication-approved artefacts may appear there. Raw or processed third-party source material must not appear merely because it was used to derive the release.

## 3. Expected publication classes

### Structured data
- JSON
- CSV
- JSONL
- Parquet

### Semantic data
- embeddings
- similarities
- optional browser-optimised semantic index

### Cards
- Markdown CauseBase Cards

### Taxonomies
- supported taxonomy definitions
- publishable mappings/crosswalks

### Governance and metadata
- schemas
- manifest
- licence/attribution material
- public correction/proposal records

## 4. Publication allowlist

Publication automation must explicitly identify allowed file classes and locations.

Do not publish arbitrary Builder output trees. Fail if unexpected file types or paths exist in the candidate.

## 5. Validation gates

A candidate should pass at least:

### Software tests
Relevant unit/integration tests.

### Entity/data invariants
Valid/unique identities, valid ABNs where applicable, plausible national counts, no catastrophic completeness regressions and financial sanity checks.

### Required-estimate invariants
For enriched cards, fundraising capability coverage is present and validates. If a fundraising value is available, its method and provenance must also validate; null is permitted when coverage records source unavailability.

### Taxonomy invariants
Taxonomy IDs, versions and term IDs exist and mappings reference valid terms.

### Card invariants
Required fields exist and schema/editorial checks pass at defined thresholds.

### Provenance invariants
Material evidence references resolve and required derivation metadata is present.

### Embedding invariants
Expected model/version/dimensions, source hash and intended vectors exist.

### Representation consistency
JSON, Parquet, CSV projections and Markdown cards agree on common canonical values.

### Publication-safety invariants
No raw annual reports, scraped HTML, unapproved source extracts, secrets, API keys, private logs or LLM debug dumps.

## 6. Drift checks

Compare with the previous successful release, including entity count, enriched-card count, DGR count, source coverage, website coverage, taxonomy coverage, fundraising-method distribution, financial completeness, embedding count and incorporated corrections.

Unexpected large changes should block or require explicit override.

## 7. Manifest

Each release should identify dataset/schema version, build time, Builder commit, source identities/dates/hashes, taxonomy versions, editorial policy version, LLM/prompt versions, embedding version, record counts, validation result, warnings, artefact hashes and previous release.

## 8. GitHub publication model

CauseBase Data is the public data repository.

Large immutable bulk distributions and historical versions should preferentially be GitHub Release assets rather than repeatedly committed binary history.

Markdown cards may live visibly in the repository if repository scale remains practical.

## 9. Viewer handoff

Viewer consumes public publication artefacts only.

Builder should emit or identify a browser-suitable current representation. Viewer must not need access to local source/processed directories.

## 10. Verification

After publication, verify expected release/assets, names/sizes, hashes where practical, latest pointers, Viewer-facing accessibility and manifest identity.

## 11. Logging and alerting

Production runs should record source-change decisions, counts processed/reused/failed, validation, publication, warnings and remote verification.

Routine no-change runs may remain quiet. Failures, blocked publications and material anomalies should alert.

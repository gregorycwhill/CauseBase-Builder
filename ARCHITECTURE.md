# CauseBase Builder Architecture

**Status:** Canonical Builder architecture; public models are provisional through the reality spike  
**Version:** 0.1

## Phase 2B longitudinal source contract

Builder persists source-native records beside, not inside, canonical cards. Each record has a source family, dataset/version, source-record ID, original field names, retrieval/observation time, effective period where known and evidence IDs. Public sidecars contain safe structured observations; raw archives, report text and private working evidence stay outside the publication bundle.

Financial records append by reporting period. A current card projection may select the latest applicable observation but must retain prior periods. Relationships support validity and observation time, so ordinary organisational change does not require a new CauseBase ID. ACNC reporting arrangements remain regulator observations, not brand/federation assertions.

The deterministic change gate returns a change profile and per-derivative reuse/refresh/undecided decision. Only an ambiguous meaning change is eligible for a bounded low-cost semantic assessment; expensive synthesis and embeddings run only after invalidation.

## 1. Architectural idea

CauseBase Builder behaves like a compiler.

It transforms heterogeneous public source material into a versioned CauseBase representation, then renders that representation into multiple public formats.

```text
SOURCE WORLD
    |
    v
ACQUIRE
    |
    v
EXTRACT / NORMALISE
    |
    v
EVIDENCE
    |
    v
DERIVE / ESTIMATE / SYNTHESISE
    |
    v
CANONICAL CAUSEBASE ENTITIES
    |
    +--> taxonomy classifications
    +--> embeddings
    +--> similarities
    |
    v
RENDER
    |
    v
VALIDATE
    |
    v
PUBLICATION CANDIDATE
```

## 2. Three storage classes

### Source

Fresh or historical copies of external material, including regulator datasets, annual/financial reports, website pages, feeds and permitted reference sources.

Source files are retained locally where useful for reproducibility and change detection. They are not automatically publishable.

### Processed

Intermediate artefacts produced by Builder: extracted text, parsed tables, cleaned web text, evidence packets, LLM inputs/outputs, estimation diagnostics, entity-resolution results and quality reports.

Processed artefacts are implementation details and may change without changing the public data contract.

### Publication

Only validated artefacts intended for CauseBase Data, including structured datasets, semantic data, taxonomies, Markdown cards, schemas, manifests and public correction records.

Only this class crosses the publication boundary.

## 3. Recommended local layout

```text
OneDrive durable archive\
  CauseBase\archive\
    sources\
      regulator\ reports\ web\ reference\
    processed\
      documents\ tables\ evidence\ entities\ metrics\ classifications\
    governed-inputs\

Local mutable runtime\
  CauseBase-runtime\
    state\ temp\ cache\ logs\ staging\

OneDrive repositories\
  CauseBase\
    charitygraph\ charitygraph-data\ charitygraph-viewer\
```

Completed durable artefacts are content-addressed or dated where practical. Downloads first complete in local temporary storage, are validated and hashed, then move to the durable archive. The exact paths are configurable; the storage classes remain explicit.

## 4. Pipeline stages

### Discover/check
Determine which remote sources or known entity sources require checking.

### Acquire
Fetch changed source material and record source identity, retrieval time, URL, HTTP metadata, content hash and licence/attribution metadata where relevant.

### Extract
Use deterministic tools first: parse structured files, extract PDF text by page, extract financial tables, strip HTML boilerplate, detect headings, find feeds/sitemaps and deduplicate text.

Website acquisition is a first-class source stage. Start with homepage, About/What we do, programs, volunteer/get involved, events, governance, news/blog, RSS/Atom and selected current-opportunity pages. Keep stable entity understanding distinct from transient current-activity evidence, with independent refresh/freshness semantics.

### Build evidence
Create compact attributable evidence objects suitable for downstream rules and LLM interpretation.

### Derive and estimate
Calculate values that can be obtained mechanically. For required estimates, follow `PROVENANCE_AND_ESTIMATION.md`.

### Synthesis
Use an LLM over selected evidence to produce structured entity understanding: neutral summary, activities, beneficiaries, geography, approaches, participation, uncertainties and evidence references.

### Apply governed correction inputs
Accepted corrections and overrides enter as governed inputs. Regenerate dependent outputs where relevant.

### Construct canonical entity/card
Assemble the public conceptual object defined in `CARD_SPEC.md`.

### Embed
Generate versioned semantic vectors from defined card representations.

### Derive similarities
Compute reproducible semantic or structured neighbourhood relationships. Similarity is descriptive navigation, not recommendation.

### Render
Render all public formats from the canonical card objects and shared derived tables.

### Validate
Run data, semantic, provenance, publication-safety and representation-consistency checks.

### Stage
Write a complete release candidate into a dedicated publication staging directory.

### Publish
Only a validated candidate may cross into CauseBase Data.

### Verify
Verify remote artefacts, hashes, release metadata and Viewer-facing current data.

## 5. Incremental processing

Builder should avoid recomputing unchanged work.

Useful identities include source content hash, cleaned evidence hash, synthesis-input hash, editorial-policy version, prompt/model version, taxonomy version and embedding version.

If inputs governing an artefact are unchanged, Builder may reuse the prior artefact.

## 6. Local state

A small local store such as SQLite may track source checks, ETags, hashes, extraction status, retries, synthesis versions, embedding versions and last successful publication.

This is operational state, not the public CauseBase database.

## 7. Production execution

Initial production is expected to run locally on Windows.

Conceptually:

```text
causebase refresh
causebase validate
causebase publish
```

Exact command names remain an implementation choice until the CLI is built.

## 8. Failure policy

Failures should be scoped where possible.

- One broken website should not invalidate fresh regulator data.
- Optional-source failure should preserve prior observations with staleness metadata.
- A material national row-count collapse should block publication.
- Missing fundraising values are publishable when explicit `not_available_from_source` (or equivalent) coverage is present; missing coverage should block publication.
- Inconsistent public representations should block publication.

## 9. Cloud/container boundary

Local execution is primary.

Cloud coding agents or containers may operate on code and representative fixtures. The complete national working corpus need not be uploaded to a cloud environment merely to make development reproducible.

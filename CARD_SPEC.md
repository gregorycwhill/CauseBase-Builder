# CauseBase Card Specification

**Status:** Provisional shared CauseBase product contract — subject to reality spike  
**Version:** 0.1-draft

## Phase 2B additions

Cards now distinguish source-native observations from canonical fields and derived artefacts. `source_native_records[]` preserves source family/version, source-record identity, observed/retrieved/effective time, source field names, explicit mappings and evidence. `financial_records[]` is longitudinal and append-only. `relationships[]` can include `valid_from`, `valid_to`, `observed_at`, confidence and status.

`funding_sources[]`, `fundraising_methods[]` and `fundraising_expenditure` are different concepts. The first records where money is evidenced to come from; the second records evidenced methods; the last is a direct or transparently derived expense value. `derivative_assessments[]` says whether an existing summary/classification/fundraising interpretation/embedding/neighbour set was refreshed or intentionally reused and why.

## 1. Purpose

The CauseBase Card is the central conceptual object in CauseBase.

It is a versioned, evidence-backed representation of one charity or other supported entity. Public CSV rows, JSON records, Parquet records, Markdown cards and Viewer displays are projections of the same underlying card.

This document defines semantics, not a final JSON Schema.

## 2. Stable identity

Every card must have a stable opaque `causebase_id`, a `subject_kind`, external identifiers and relevant relationships. It must not use ABN or ACNC ID as its universal primary identity.

- `causebase_id`;
- `subject_kind`: `organisation`, `organisation_group`, `legal_entity`, `organisational_unit`, `fund` or `program`;
- `external_identifiers[]`, including ABN, ACNC registration ID, ACN, website/domain or future identifiers where applicable;
- `registrations[]` and `tax_statuses[]`; these are roles/statuses, not subject kinds;
- `relationships[]`, where a public-facing organisation, legal entity, fund, branch, program or operating unit does not map one-to-one to an external record;
- current legal name;
- display/common name where available;
- entity status;
- card version/build metadata.

Relationships may include `registered_as`, `operates_as`, `part_of`, `branch_of`, `program_of`, `auspiced_by` and `successor_to`. A branded group and its constituents are both addressable only when evidence supports the relationship; names alone never create an aggregate.

Every source record keeps its own stable identity. Its resolution to a CauseBase subject records status (`resolved`, `candidate`, `ambiguous`, `unresolved`), basis, confidence, supporting/conflicting signals and review state. Medium-confidence or ambiguous matches cannot silently populate a card.

## 3. Identity and contact

Potential fields include legal/display names, aliases, ABN, ACNC status, DGR status/type, website, appropriate public contact details, registered address, operating locations, service geography and external identifiers.

Do not expand public contact information into unnecessary personal information.

## 4. CauseBase summary

A concise CauseBase-authored synthesis answering what the organisation actually does, for whom, where, and through which principal activities or approaches.

The summary follows `EDITORIAL_POLICY.md`.

## 5. Organisation self-description

Where useful, retain separately the organisation-stated mission, purpose or short description. These are attributed self-report and do not replace CauseBase's neutral summary.

## 6. Activities and operating model

Represent concrete supported attributes such as services, programs, activities, approaches, delivery modes, beneficiaries, geographic scope and organisational character.

## 7. Participation

Represent observed ways a person can engage, including donate, volunteer, working bee, event, membership, board/committee roles and other participation.

Distinguish stable participation modes from transient opportunities.

A transient opportunity should support title, type, location, dates, recurrence, commitment, skills where available, source/application URL, first/last seen and freshness/status.

## 8. Financials

Cards may include revenue, donations/bequests, government grants, employee costs, total expenses, assets, liabilities, staff/volunteer information and derived metrics.

Financial values belong to a reporting scope, rather than being copied to every related subject. A financial record records its source, start/end dates, derivable length, label, non-standard/transition flag, reporting subject, covered subjects, consolidation state, attribution method and evidence. A group card may own a consolidated total; a constituent must not inherit it without an explicit, evidenced allocation.

A directly observed amount is not a bare float: it retains exact-decimal source amount, source currency, source unit scale, exact-decimal normalised amount, normalised currency and relevant source presentation metadata. Report values in `$ '000` and AIS raw-dollar values therefore remain auditable and comparable. Currency conversion is a separate explicit derivation, never an implicit normalisation.

Financial metric sets retain every legitimate source observation and an explicit reconciliation status: `single_observation`, `agreeing`, `precision_consistent`, `divergent`, `non_comparable` or `unresolved`. A divergent or unresolved set is known data, not missing data; it must not be collapsed to one displayed or analytical scalar without a separate, explicit policy.

## 9. Fundraising expenditure

For an enriched card, fundraising expenditure is a required capability/coverage state. The value may be unavailable/null when the source does not support a defensible estimate.

Represent:

- estimated value;
- period;
- currency;
- estimate method;
- confidence;
- components where relevant;
- rule/model identifier where relevant;
- evidence references;
- optional plausible range;
- notes required to interpret the estimate.

Never encode an imputed value as though it were directly reported.

## 10. Classifications

Each classification identifies taxonomy ID, taxonomy version, term ID, assignment method, provenance/evidence and confidence where relevant.

No single taxonomy field is treated as the universal classification of the charity.

## 11. Evidence

Material card content should be capable of linking to evidence objects containing source type/ID, title, publisher, URL, reporting period, observation date, page/section/table reference, content hash or snapshot ID and licence metadata where relevant.

Public cards need not reproduce source text where rights or usefulness argue against it.

## 12. Epistemic status

Where material, distinguish direct authoritative fact, organisation self-report, independent report, community evidence, deterministic derivation, heuristic estimate, LLM interpretation and statistical imputation.

Confidence is not a replacement for method.

## 13. Corrections and contestability

Cards may link to active correction proposals, accepted-correction provenance, disputed classifications and relevant discussion.

The card itself remains compiled output.

## 14. Semantic representation

A card may have one or more embeddings.

Embedding metadata includes embedding ID, entity ID, embedding type, model/version, dimensions, source representation/hash, generation date and vector reference.

The raw high-dimensional vector need not appear inside Markdown cards.

## 15. Similarity

Derived similarity records may include source entity, similar entity, similarity type, score, rank, method/version and corpus version.

Similarity does not imply recommendation or quality.

## 16. Freshness

A card should expose card build date, important source observation dates, freshness of transient information and whether information is retained from prior observations.

## 17. Build metadata

Every card should be attributable to a CauseBase release and relevant methodology versions, including dataset, schema/card, generator, editorial policy, prompt/model, taxonomy and embedding versions where applicable.

## 18. Publication projections

### JSON
Rich structured representation suitable for software and Viewer use.

### JSONL
Streaming/agent/data-processing representation.

### Parquet
Efficient analytical representation.

### CSV
Flattened convenience projection. CSV must not define the canonical card model.

### Markdown
Human- and LLM-readable rendering of the card. It should reference rather than print large machine-native vectors.

## 19. Coverage and card invariants

Represent explicit coverage observations rather than treating `registered`, `thin`, `enriched` or `rich` as the primary truth. Each observation identifies a subject capability plus relevant source record and one of: `observed`, `not_found_in_source`, `not_available_from_source`, `not_applicable`, `retrieval_failed`, `not_yet_processed`, `stale` or `unknown`. A derived enrichment label may remain a convenience only.

An enriched card must:

- have stable opaque CauseBase identity;
- have a CauseBase summary;
- identify evidence/freshness;
- have fundraising-expenditure coverage; when a value is present, include its method/provenance;
- use valid taxonomy IDs/terms;
- identify relevant build versions;
- be derivable into all required public representations;
- contain no recommendation or quality rating.

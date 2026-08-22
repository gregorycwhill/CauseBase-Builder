# CharityGraph Taxonomy Model

**Status:** Canonical taxonomy contract  
**Version:** 0.1

## 1. Principle

CharityGraph is multi-taxonomy by design.

A charity exists independently of any classification scheme. A classification is an assertion that an entity maps to a term under a named, versioned taxonomy.

## 2. Supported taxonomy classes

CharityGraph may support:

- CharityGraph-maintained taxonomies;
- ACNC schemes;
- recognised external or academic schemes;
- international schemes;
- funder taxonomies;
- community-contributed schemes;
- experimental schemes.

Supporting a taxonomy does not imply endorsement.

## 3. Taxonomy identity

Each taxonomy should define taxonomy ID, name, version, publisher/maintainer, description, source URL, licence and status.

Potential statuses include CharityGraph-maintained, official, recognised external, community-maintained, experimental and deprecated.

## 4. Terms

Each term should have stable term ID, label, definition, optional parent/broader term, aliases/synonyms, optional notes and taxonomy/version identity.

## 5. Classification assertions

An entity classification identifies entity ID, taxonomy ID/version, term ID, assignment method, evidence/provenance, confidence where relevant and assignment/build date.

Assignment methods may include source-native, deterministic mapping, LLM classification, human/community contribution and imported external mapping.

## 6. CharityGraph taxonomy design

The native CharityGraph taxonomy should optimise for discovery and machine understanding, not mimic ACNC structure.

It should consider separating dimensions that regulator schemes often collapse, including:

- cause/problem domain;
- beneficiary/population;
- activity;
- operating approach;
- involvement/participation;
- geography;
- organisational character where useful.

The exact native taxonomy is a separate design task.

## 7. Cross-taxonomy mappings

Mappings should preserve relationship type, including exact, close, broader, narrower and related matches.

Do not assume similar labels mean identical concepts.

## 8. LLM classification

LLMs may assign classifications where no existing classification exists.

Rules:

- provide candidate terms/definitions rather than invite invented labels;
- use supplied evidence only;
- allow multiple terms where permitted;
- allow uncertainty;
- do not force a term merely to avoid null;
- record model/prompt/method;
- preserve evidence references.

Candidate retrieval may use lexical or embedding methods so the full ontology need not be supplied in every request.

## 9. Community taxonomies

Third parties may contribute/maintain taxonomies if definitions are explicit, stable IDs exist, versioning is possible, licence permits redistribution/use and maintainer/provenance is identified.

Community taxonomies remain distinct namespaces.

## 10. Versioning

Distinguish label/editorial changes, definition changes, added/deprecated terms, hierarchy changes and mapping changes.

Material semantic changes require a new taxonomy version.

## 11. Viewer behaviour

Viewer may let users filter by taxonomy, inspect multiple schemes side-by-side, switch lenses, inspect mappings and challenge a classification.

Viewer must not present one taxonomy as universally correct merely because it is the default selection.

## 12. Governed taxonomy maintenance

The executable workflow and private-artifact contract are documented in
[`TAXONOMY_REVIEW_WORKFLOW.md`](TAXONOMY_REVIEW_WORKFLOW.md).

Per-card classification and taxonomy maintenance are separate operations:

```text
EVIDENCE
  ↓
CARD SYNTHESIS
  ↓
CURRENT TAXONOMY CLASSIFICATION
  ↓
PRIVATE TAXONOMY PRESSURE SIGNALS
  ↓
PERIODIC CORPUS REVIEW
  ↓
CHANGE PROPOSALS
  ↓
HUMAN GOVERNANCE
  ↓
NEW TAXONOMY VERSION
  ↓
RECLASSIFICATION
```

Taxonomy maintenance is a durable, private, human-governed workflow. Its
required first stage is deterministic and makes no API call:

```text
charitygraph taxonomy-review-prepare
  -> compact review-summary.json, pressure-report.md and empty decision record
```

PREPARE records exact corpus/taxonomy hashes, taxonomy and dimension
diagnostics, private taxonomy-pressure coverage, deterministic bounded
representative cases and questions for people. It is not a proposal generator.
It never writes canonical taxonomy files or cards. The sampling cap prevents a
future reviewer from receiving the whole corpus by accident.

`charitygraph taxonomy-review-model-review` is optional advisory analysis of that
compact packet. Its output is deliberately separate from the human decision
record and records model, reasoning setting, input hash, token usage and cost
privately. A model finding cannot create a taxonomy change. The legacy
`causebase taxonomy-review` v0.1 packages remain historical advisory evidence.

Humans record governed outcomes (`approve`, `reject`, `defer`, `watch`,
`request_more_evidence`, or `modify`) in `decision-record.json`; use
`charitygraph taxonomy-review-render-decisions` to render them as Markdown. Only
then may a separately implemented candidate taxonomy be checked with
`charitygraph taxonomy-review-validate`. VALIDATE compares baseline/candidate and
decisions, estimates current-card impact and required rebuilds, but does not
regenerate, reclassify or publish anything.

ACNC classifications, labels, mappings and cohort strata are excluded from
native PREPARE pressure inputs. They may only be examined separately as a
post-hoc diagnostic. Private `unmapped_concepts` and
`taxonomy_ambiguities` remain noncanonical maintenance observations; absence
on older cards means coverage is unavailable, not that no pressure exists.

Future synthesis may retain private `unmapped_concepts` and
`taxonomy_ambiguities` signals. They are not classifications, cannot invent
term IDs, and are excluded from public card serialisation.

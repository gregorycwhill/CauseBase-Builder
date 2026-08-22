# Durable taxonomy review workflow

Taxonomy maintenance is governed separately from per-card classification.
The frozen `charitygraph` taxonomy `0.1-phase2a` remains unchanged until a human
authorises and implements a new version.

## 1. Prepare

Run the required, deterministic stage against a private corpus:

```powershell
charitygraph taxonomy-review-prepare --corpus <charitygraph.json> --taxonomy <baseline.json> --output <private-review-directory> [--similarities <similarities.json>] [--previous-review <packet-or-reference>]
```

It creates `review-summary.json`, `pressure-report.md`, an empty
`decision-record.json`, `decisions.md` and `migration-report.md`. The summary
contains hashes/provenance, frozen taxonomy details, deterministic term and
dimension diagnostics, private pressure-signal coverage, at most 40 derived
representative cases, and questions for human review. It does not produce a
candidate taxonomy or invoke OpenAI.

ACNC classifications, labels, mappings and cohort strata are not native
pressure inputs. `unmapped_concepts` and `taxonomy_ambiguities` are private
maintenance signals, never public classifications; old cards without them are
reported as missing coverage.

## 2. Optional model review

Only after PREPARE, a reviewer may request bounded advice:

```powershell
charitygraph taxonomy-review-model-review --review-summary <review-summary.json> --output <private-directory> --model <approved-model> --reasoning-effort high
```

This writes `model-review-advisory.json` and private telemetry separately. It
cannot write a decision record, change taxonomy files, cards, embeddings or
Viewer assets. Treat findings and counterexamples as evidence for people, not
as decisions.

## 3. Human decision and validation

Record only human outcomes in `decision-record.json`: `approve`, `reject`,
`defer`, `watch`, `request_more_evidence`, or `modify`. Each record supplies
the review and pressure IDs, semantic decision, rationale, boundaries,
exclusions, representative cases and migration implications. Render it with:

```powershell
charitygraph taxonomy-review-render-decisions --decision-record <decision-record.json> --output <decisions.md>
```

After a separately implemented candidate taxonomy exists, run:

```powershell
charitygraph taxonomy-review-validate --corpus <charitygraph.json> --baseline-taxonomy <baseline.json> --candidate-taxonomy <candidate.json> --decision-record <decision-record.json> --output <private-validation.json>
```

VALIDATE is deterministic and non-mutating. It reports term changes, current
assignment impact and required downstream rebuilds. It does not reclassify or
regenerate any corpus artefact.

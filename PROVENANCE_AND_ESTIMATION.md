# Provenance and Estimation

**Status:** Provisional shared CauseBase methodology contract — subject to reality spike  
**Version:** 0.1-draft

## 1. Principle

CauseBase should provide useful conclusions without hiding how they were obtained. Provenance is part of the data model.

## 2. Source classes

CauseBase distinguishes:

- regulatory/authoritative;
- organisation self-report;
- independent reference;
- community contribution;
- CauseBase derivation.

## 3. Derivation classes

At minimum distinguish:

- `direct_extract`
- `deterministic_derivation`
- `heuristic_estimate`
- `llm_interpretation`
- `peer_imputation`
- `fallback_prior`

Names may change when the machine schema is defined; the distinctions should not.

## 4. Evidence references and granularity

Evidence references should identify enough information to reconstruct the basis of a claim where practical: source ID/type/URL, title, publisher, reporting period, observed date, document hash, page, table, section or structured-source field.

Granularity is field-appropriate. Regulatory facts may cite a source dataset and field; fundraising estimates require direct/component and report-page/table detail; taxonomy assignments require evidence plus taxonomy/version/method; activity lists require evidence references; summaries should use sentence- or section-level evidence where practical. Do not create a microscopic globally identified claim graph before the reality spike demonstrates that need.

## 4a. Resolution and source-record provenance

Source records are preserved independently of CauseBase subjects. Every resolution records its status, basis, confidence, supporting signals, conflicts and review status. An authoritative identifier with unambiguous corroboration may resolve automatically; name-only matching is conservative, and an LLM is never the sole resolver.

## 4b. Monetary observations

Directly observed financial amounts retain exact-decimal source amount, source currency, source unit scale, exact-decimal normalised amount and normalised currency. The normalised value must equal source amount multiplied by source scale. Source labels such as `$ '000`, raw text and precision remain available where useful. Currency conversion is a separate derived operation with its own source/rate/date/method provenance; CauseBase does not silently convert foreign currency.

## 5. Confidence

Confidence expresses uncertainty about an interpretation or estimate. It must not conceal method.

A small controlled vocabulary such as `high`, `medium`, `low` may initially be more honest than false numerical precision.

## 6. Required-estimate ladder

### Level 1 — Direct disclosure
Use an explicit source value.

### Level 2 — Deterministic reconstruction
Calculate from clearly identified components.

### Level 3 — Documented heuristic
Use an explicit CauseBase rule and publish the components/rule.

### Level 4 — LLM interpretation
Use selected financial tables/notes where a mechanical rule cannot confidently resolve the presentation.

The model must return estimate, included/excluded components, evidence references, method and uncertainty. It must not invent values absent from evidence.

### Level 5 — Peer imputation
Estimate from a defined comparator group using attributes such as size/revenue, cause/activity, funding structure, geography, organisational character or semantic neighbourhood.

Publish peer definition, peer count, statistic, calculation and uncertainty range where available.

### Level 6 — Fallback prior
Where evidence and meaningful peers are insufficient, use a documented broad prior. This is the weakest permissible estimate and should be conspicuously labelled.

## 7. Fundraising expenditure

Fundraising expenditure is a key required CauseBase estimate for enriched entities.

Potential direct/component labels may include fundraising, appeals, donor acquisition, development, marketing, advertising, promotion, public relations, fundraising events, supporter engagement and relevant communications expenditure.

These labels do not imply automatic inclusion. Rules should define context-sensitive treatment.

## 8. Blank policy

For required estimates, blank is not a neutral outcome.

A blank indicates the pipeline has not completed the estimation ladder or has reached a defined hard-failure state.

For ordinary optional observations, unknown/null may be valid.

## 9. Plausible ranges

Heuristic and imputed estimates may publish a plausible range. Prefer empirically derived peer ranges to invented intervals.

Do not describe them as formal confidence intervals unless they actually are.

## 10. Source retention and public citation

Raw third-party documents may be retained locally without public redistribution.

Public CauseBase may cite source URL, title, reporting period, page/table and content hash/snapshot identity.

## 11. Contradictions

Do not silently collapse contradictory evidence. Prefer current credible evidence for current-state fields and flag unresolved contradiction where material.

## 12. Reproducibility

Derived values should record rule/model/version information sufficient to reproduce or explain them under the corresponding build.

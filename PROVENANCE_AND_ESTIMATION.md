# Provenance and Estimation

**Status:** Canonical Builder guidance aligned to CauseBase Data authority

## Principle

CauseBase publishes useful conclusions without hiding how they were obtained.
Provenance is part of the data model, and absence is not evidence of zero.

## Source classes

CauseBase distinguishes regulatory/authoritative, organisation self-report,
independent reference, community contribution and CauseBase derivation.

## Derivation classes

The generic vocabulary includes `direct_extract`, `deterministic_derivation`,
`heuristic_estimate`, `llm_interpretation` and `peer_imputation`. Peer imputation
is retained only for separately approved future domains; it is prohibited for
fundraising expenditure. There is no `fallback_prior` publication method.

## Evidence and money

Evidence references should identify source ID/type/URL, title, publisher, reporting
period, observed date, document hash, page/table/section or structured field where
practical. Monetary observations retain exact source amount, currency, unit scale,
normalised amount/currency and raw value. Currency conversion is an explicit derived
operation with its own provenance.

## Confidence and fundraising ladder

Confidence expresses uncertainty and must not conceal method. Fundraising expenditure
uses this governed ladder:

1. **Direct disclosure:** use an explicit source value.
2. **Deterministic reconstruction:** calculate from clearly identified components.
3. **Bounded or governed interpretation:** use defensible attribution bounds or a
   specifically governed interpretation, with included/excluded components, rule and
   evidence references.
4. **Unavailable/null:** when no defensible value exists, return `null` and persist
   explicit coverage such as `not_available_from_source`.

The pipeline must not invent values absent from evidence. Universal priors,
peer-imputation fill, forced midpoint and forced point estimate are prohibited for
fundraising expenditure. A null value is valid when its coverage state is explicit.

## Fundraising expenditure

Fundraising expenditure is a key capability for enriched entities, not a guaranteed
scalar. Direct/component labels may include fundraising, appeals, donor acquisition,
development, marketing, advertising, promotion, public relations, fundraising events,
supporter engagement and relevant communications expenditure. Labels do not imply
automatic inclusion; rules define context-sensitive treatment.

If a value is published, include method, confidence, evidence, components/rule and
any supported plausible range. Do not manufacture an interval or midpoint.

## Reproducibility and contradictions

Derived values record rule/model/version information sufficient to explain or
reproduce them. Contradictory evidence remains visible with reconciliation status;
it is not silently collapsed into a scalar.

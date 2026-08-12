# CauseBase Editorial Policy

**Status:** Canonical editorial and LLM synthesis policy  
**Version:** 0.1

## Phase 2B provenance presentation

Write natural CauseBase prose for concrete, well-supported descriptive facts. Put ordinary provenance in structural citations, linked evidence and field metadata rather than repeating “the website says” or “filings show” in each sentence. Retain explicit attribution for mission statements, claimed outcomes, evaluation, contested claims and forward-looking organisation-authored assertions. Financial values belong primarily in structured sections; never make an estimate look directly reported.

## 1. Purpose

CauseBase produces neutral, information-dense descriptions of Australian charities from public evidence.

Descriptions help humans and machines understand what an organisation does, who it serves, where it operates and how people can participate.

CauseBase does not write promotional copy and does not reproduce an organisation's preferred positioning as CauseBase voice.

## 2. Prefer concrete description to aspiration

Prefer:

> Runs monthly volunteer working bees involving weed removal, litter collection and revegetation along Merri Creek in northern Melbourne.

Over:

> Empowers communities to create a healthier and more sustainable world through community-led environmental action.

## 3. Distinguish self-description from CauseBase description

Organisation-authored mission or positioning may be represented separately and attributed. It must not automatically become an unqualified CauseBase assertion.

## 4. Use the lowest useful level of abstraction

Prefer specific activities over broad moral or strategic abstractions where evidence permits.

Prefer:

> Provides free migration-law advice and representation to asylum seekers.

Over:

> Advances human rights.

Broader concepts may still appear as taxonomy classifications.

## 5. Avoid promotional and evaluative language

Do not describe an organisation or program as leading, innovative, transformative, outstanding, impactful, effective, vital, inspiring or world-class unless necessary to accurately attribute an external statement.

Do not infer quality from size, longevity, professional communications or prominence.

## 6. Do not infer impact from activity

Evidence of an activity is not evidence of effectiveness.

Prefer:

> Provides literacy tutoring to children.

Do not write:

> Improves children's educational outcomes.

unless outcome evidence supports it.

## 7. Preserve uncertainty

When evidence is conflicting, incomplete or ambiguous, do not silently resolve it. Absence of evidence is not evidence of absence.

## 8. Prefer current evidence for current descriptions

Current credible evidence normally outweighs older material when describing current operations.

## 9. Treat source types differently

Distinguish regulatory/official, organisation self-report, independent reference, community contribution, mechanical derivation, heuristic estimate, LLM interpretation and statistical imputation.

## 10. Identity-sensitive and contested claims

Do not assign political, cultural, identity or controversial characteristics merely because associated language appears in promotional material. Prefer attribution and concrete evidence.

## 11. Corrections versus positioning

Charities may correct facts, stale information, missing activity, geography, identity, classifications and unsupported inference.

CauseBase is not required to replace neutral prose with preferred PR language.

## 12. Common descriptive standard

Large and small organisations should receive the same editorial treatment. Sophisticated communications must not produce more flattering or abstract CauseBase prose.

## 13. Dense writing

Every sentence should materially distinguish the organisation. Prefer concrete nouns, verbs, places, quantities, populations and frequencies.

## 14. Recommendation boundary

CauseBase text must not recommend support, rank organisations, encourage donations, imply moral worth or imply that similarity means preference.

## 15. LLM synthesis rules

When generating CauseBase text:

1. Use only supplied evidence.
2. Describe demonstrable activity before aspiration.
3. Prefer concrete verbs, nouns, places, populations, quantities and frequencies.
4. Remove promotional adjectives and generic mission language.
5. Do not copy source wording unnecessarily.
6. Do not infer effectiveness, importance, popularity or moral worth.
7. Attribute organisation claims.
8. Preserve material uncertainty and contradictions.
9. Prefer recent evidence for current operations.
10. Separate current from historical activities.
11. Do not invent missing facts to make prose complete.
12. For required estimates, state method/provenance through structured fields.
13. Use only supplied taxonomy IDs and definitions.
14. Do not force unsupported classifications.
15. Keep summaries dense.
16. Avoid generic prose.
17. Do not recommend, rank or persuade.
18. Write in plain Australian English.

The target question is:

> What does this organisation actually do, for whom, where, and how?

Not:

> How would this organisation describe itself in a grant application?

## 16. Regression examples

Builder should maintain a small human-reviewed editorial regression corpus containing source evidence, acceptable output, unacceptable output and explanation.

Model or prompt changes should be evaluated against this corpus before national regeneration.

# CauseBase Corrections and Community Inputs

**Status:** Provisional shared CauseBase correction model  
**Version:** 0.1-draft

## 1. Principle

CauseBase is corrigible by design.

Published records are generated artefacts. Users propose corrections; they do not directly edit public generated data.

## 2. Correction types

A proposal may concern factual correction, stale information, missing information, organisation self-description, classification dispute, methodology dispute, evidence addition or entity-resolution error.

## 3. Basic intake, moderation and proposal identity

The first public enriched-card release must provide low-friction private intake with prefilled CauseBase subject, field/assertion and release context, plus a traceable acknowledgement or proposal identifier.

Raw submissions are private. They may contain personal information, abuse, private contact details, defamatory allegations or sensitive material. Moderation/review produces the governed public proposal record where publication is appropriate.

Every governed proposal should receive a stable public ID and record CauseBase subject ID, target assertion, dataset/card version challenged, current/proposed value, reason, evidence, dates, status, review history, decision and incorporated release where applicable.

## 4. Status model

Initial statuses:

- `lodged`
- `under_review`
- `queried`
- `accepted`
- `rejected`
- `incorporated`

## 5. Append-only history

Correction history should normally be append-only.

Exceptions may be required for privacy, abuse, legal issues, spam or accidental publication of sensitive information. Public contestability concerns governed proposal and decision records, not every byte of raw intake.

## 6. Accepted corrections

Accepted corrections should become governed Builder inputs.

Preferred:

```text
published card
  -> proposal
  -> accepted evidence/override
  -> Builder input
  -> regenerate dependent understanding
  -> validate
  -> next release
```

Avoid manually overwriting final JSON/Markdown.

## 7. Dependency regeneration

A changed activity may require regeneration of summary, activity lists, taxonomy assignments, embeddings and similarities.

A corrected financial figure may require regeneration of ratios, fundraising estimates, peer groups and displayed metrics.

## 8. Organisation self-description

An organisation may submit its current mission/self-description. This can be represented as attributed organisation voice and does not automatically replace CauseBase's neutral description.

## 9. Classification disputes

A classification correction must identify taxonomy, version, term, proposed change and reason/evidence.

## 10. Intake channels

Possible channels include simple public form, GitHub issue/PR, Viewer field-level correction and future APIs.

All channels should converge on the same proposal model. The intake channel is not the canonical correction datastore.

## 11. Public discussion

Open-ended discussion is distinct from a correction proposal. Discussion can lead to evidence or a formal proposal but does not automatically mutate CauseBase.

## 12. Licensing of contributions

Contribution UX should state that submitted material intended for incorporation may be reproduced, modified and redistributed under CauseBase's applicable open-data terms.

Do not assume arbitrary linked third-party text becomes openly licensable.

## 13. Review principles

Prefer verifiable current evidence, precise correction, transparent methodology, neutral description and clear provenance.

Resist promotional rewrites, unsupported impact claims, attempts to suppress accurate public facts and attempts to game classification/similarity.

## 14. Publication

Public correction status/history is part of CauseBase's contestability model.

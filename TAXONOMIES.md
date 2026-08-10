# CauseBase Taxonomy Model

**Status:** Canonical taxonomy contract  
**Version:** 0.1

## 1. Principle

CauseBase is multi-taxonomy by design.

A charity exists independently of any classification scheme. A classification is an assertion that an entity maps to a term under a named, versioned taxonomy.

## 2. Supported taxonomy classes

CauseBase may support:

- CauseBase-maintained taxonomies;
- ACNC schemes;
- recognised external or academic schemes;
- international schemes;
- funder taxonomies;
- community-contributed schemes;
- experimental schemes.

Supporting a taxonomy does not imply endorsement.

## 3. Taxonomy identity

Each taxonomy should define taxonomy ID, name, version, publisher/maintainer, description, source URL, licence and status.

Potential statuses include CauseBase-maintained, official, recognised external, community-maintained, experimental and deprecated.

## 4. Terms

Each term should have stable term ID, label, definition, optional parent/broader term, aliases/synonyms, optional notes and taxonomy/version identity.

## 5. Classification assertions

An entity classification identifies entity ID, taxonomy ID/version, term ID, assignment method, evidence/provenance, confidence where relevant and assignment/build date.

Assignment methods may include source-native, deterministic mapping, LLM classification, human/community contribution and imported external mapping.

## 6. CauseBase taxonomy design

The native CauseBase taxonomy should optimise for discovery and machine understanding, not mimic ACNC structure.

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

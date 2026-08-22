# CharityGraph

CharityGraph is the local, reproducible production engine for provenance-aware Australian charity data. It creates and validates source-native records, canonical observations, evidence, and derived publication projections for [CharityGraph Data](https://github.com/gregorycwhill/charitygraph-data).

The active command is `charitygraph`; `causebase` is a warning-emitting legacy alias scheduled for removal at the next pre-1.0 breaking release. New configuration uses `CHARITYGRAPH_ARCHIVE_ROOT`, `CHARITYGRAPH_RUNTIME_ROOT`, and `CHARITYGRAPH_DATA_REPOSITORY`.

## Publication model

Source-native records and canonical observations carry provenance and epistemic semantics. JSON/Markdown cards and their sidecars are authoritative; CSV and Parquet are projections. Builder never publishes raw source archives, annual-report PDFs, web snapshots, credentials, or private runtime outputs.

## Legacy material

The immutable 0.5 and pre-pivot pipeline remains available only for historical verification and compatibility. It retains its original `causebase_id` fields and release artefact names. See [CharityGraph Data's migration guide](https://github.com/gregorycwhill/charitygraph-data/blob/main/docs/migration/causebase-to-charitygraph.md).

## Development

Run `python -m pytest` for the Builder suite and `python -m charitygraph --help` for the canonical CLI. Current component guidance is in `AGENTS.md`; shared project state and planning live in CharityGraph Data.

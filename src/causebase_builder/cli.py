from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_paths
from .pipeline import build_fixture_corpus
from .render import render_publication
from .sources.documents import extract_pdf_evidence
from .sources.reality_spike import map_ais_coverage, resolve_cohort, resolve_report_abns
from .sources.web import extract_web_snapshot
from .registry import SubjectRegistry
from .national import build_national_backbone, validate_structured_backbone
from .validate import mark_manifest_validated, validate_publication
from .taxonomy_review import run_taxonomy_review
from .taxonomy_workflow import model_review, prepare_review, render_decisions, validate_implemented_change
from .phase2b import project_phase2b
from .phase2c import project_phase2c
from .document_v2.evaluate import run_benchmark


def build_demo(args: argparse.Namespace) -> int:
    source = Path(args.source)
    output = Path(args.output)
    cards, vectors, similarities = build_fixture_corpus(
        source_path=source,
        dataset_version=args.dataset_version,
    )
    if args.registry:
        registry_errors = SubjectRegistry.load(Path(args.registry)).validate_card_bindings(cards)
        if registry_errors:
            print("BUILD FAILED REGISTRY VALIDATION")
            for error in registry_errors:
                print(f"- {error}")
            return 2
    render_publication(
        cards,
        vectors,
        similarities,
        output,
        require_parquet=not args.allow_missing_parquet,
    )
    errors = validate_publication(output)
    mark_manifest_validated(output, errors)
    if errors:
        print("BUILD FAILED VALIDATION")
        for error in errors:
            print(f"- {error}")
        return 2

    print(f"Built and validated {len(cards)} fixture CauseBase cards")
    print(f"Publication candidate: {output.resolve()}")
    return 0


def validate_existing(args: argparse.Namespace) -> int:
    output = Path(args.output)
    errors = validate_publication(output)
    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 2
    print("Validation passed")
    return 0


def project_phase2b_release(args: argparse.Namespace) -> int:
    output = Path(args.output)
    project_phase2b(Path(args.input), output, args.dataset_version, archive_root=Path(args.archive_root), cache_root=Path(args.cache_root), model=args.model)
    errors = validate_publication(output)
    mark_manifest_validated(output, errors)
    if errors:
        print("PHASE 2B PROJECTION FAILED VALIDATION")
        for error in errors:
            print(f"- {error}")
        return 2
    print(f"Built Phase 2B candidate {args.dataset_version}: {output.resolve()}")
    return 0


def project_phase2c_release(args: argparse.Namespace) -> int:
    output = Path(args.output)
    project_phase2c(Path(args.input), output, args.dataset_version, archive_root=Path(args.archive_root), embedding_cache_root=Path(args.embedding_cache_root) if args.embedding_cache_root else None)
    errors = validate_publication(output)
    mark_manifest_validated(output, errors)
    if errors:
        print("PHASE 2B RC4 PROJECTION FAILED VALIDATION")
        for error in errors: print(f"- {error}")
        return 2
    print(f"Built Phase 2B RC4 candidate {args.dataset_version}: {output.resolve()}")
    return 0


def show_paths(args: argparse.Namespace) -> int:
    paths = load_paths(Path(args.workspace).resolve())
    print(f"archive_root={paths.archive_root}")
    print(f"runtime_root={paths.runtime_root}")
    print(f"data_repository_root={paths.data_repository_root}")
    return 0


def benchmark_golden(args: argparse.Namespace) -> int:
    report = run_benchmark(Path(args.corpus), archive_root=Path(args.archive_root) if args.archive_root else None, runtime_root=Path(args.runtime_root), gold_card=Path(args.gold_card) if args.gold_card else None)
    print(f"Golden Corpus v{report['corpus_version']} benchmark: {report['decision_classification']}")
    print(f"Private reports: {Path(args.runtime_root).resolve()}")
    return 0


def resolve_reality_spike(args: argparse.Namespace) -> int:
    result = resolve_cohort(
        Path(args.cohort),
        Path(args.acnc_csv),
        Path(args.source_inventory) if args.source_inventory else None,
        Path(args.identifier_evidence) if args.identifier_evidence else None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Resolved {len(result['results'])} discovery seeds")
    print(f"Wrote conservative resolution report: {output.resolve()}")
    return 0


def extract_report(args: argparse.Namespace) -> int:
    result = extract_pdf_evidence(
        Path(args.pdf), max_pages=args.max_pages, start_page=args.start_page
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"Extracted {result['extracted_page_count']}/{result['page_count']} report pages "
        f"to {output.resolve()}"
    )
    return 0


def map_ais(args: argparse.Namespace) -> int:
    result = map_ais_coverage(Path(args.resolution_report), Path(args.ais_csv))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote AIS coverage report: {output.resolve()}")
    return 0


def extract_web(args: argparse.Namespace) -> int:
    source = Path(args.html)
    text = extract_web_snapshot(source.read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"source_file": source.name, "readable_text": text}, indent=2),
        encoding="utf-8",
    )
    print(f"Extracted web snapshot to {output.resolve()}")
    return 0


def resolve_reports(args: argparse.Namespace) -> int:
    result = resolve_report_abns(
        [Path(path) for path in args.extract],
        Path(args.acnc_csv),
        Path(args.source_inventory) if args.source_inventory else None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote report/ACNC resolution report: {output.resolve()}")
    return 0


def promote_subject(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.resolution_report).read_text(encoding="utf-8"))
    result = next(item for item in report["results"] if item["seed_name"] == args.seed_name)
    supported_abns = {
        signal.removeprefix("ABN:")
        for signal in result.get("supporting_signals", [])
        if signal.startswith("ABN:")
    }
    supported_candidates = [
        candidate
        for candidate in result["candidates"]
        if any(
            identifier["scheme"] == "abn" and identifier["value"] in supported_abns
            for identifier in candidate["external_identifiers"]
        )
    ]
    source_record_ids = [
        item["source_record_id"]
        for item in (supported_candidates or result["candidates"])
    ]
    registry = SubjectRegistry.load(Path(args.registry))
    subject = registry.mint(
        display_name=args.display_name or result["seed_name"],
        subject_kind=args.subject_kind,
        resolution_status=result["resolution_status"],
        resolution_basis=result["resolution_basis"],
        source_record_ids=source_record_ids,
    )
    registry.save()
    print(f"Promoted {result['seed_name']} as {subject['causebase_id']}")
    return 0


def build_national(args: argparse.Namespace) -> int:
    diagnostics = build_national_backbone(
        acnc_csv=Path(args.acnc_csv), acnc_metadata=Path(args.acnc_metadata),
        ais_csv=Path(args.ais_csv), ais_metadata=Path(args.ais_metadata),
        dgr_observations=Path(args.dgr_observations) if args.dgr_observations else None,
        dgr_bulk_zips=[Path(path) for path in args.dgr_bulk_zip] if args.dgr_bulk_zip else None,
        dgr_metadata=Path(args.dgr_metadata) if args.dgr_metadata else None,
        registry_path=Path(args.registry), private_output=Path(args.private_output),
        public_output=Path(args.public_output),
    )
    errors = validate_structured_backbone(Path(args.public_output))
    manifest_path = Path(args.public_output) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation"] = {"status": "passed" if not errors else "failed", "errors": errors}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if errors:
        print("BUILD FAILED VALIDATION")
        for error in errors: print(f"- {error}")
        return 2
    print(f"Built national backbone: {diagnostics['source_row_counts']}")
    return 0


def taxonomy_review(args: argparse.Namespace) -> int:
    result = run_taxonomy_review(
        corpus_path=Path(args.corpus), taxonomy_path=Path(args.taxonomy), output_dir=Path(args.output),
        similarities_path=Path(args.similarities) if args.similarities else None, model=args.model,
        reuse_blind_review=Path(args.reuse_blind_review) if args.reuse_blind_review else None,
    )
    review = result["taxonomy_review"]
    print(
        f"Completed governed taxonomy review of {review['corpus_subject_count']} cards against "
        f"{review['baseline_taxonomy_version']}; proposals remain pending human decision."
    )
    print(f"Private review package: {Path(args.output).resolve()}")
    return 0


def taxonomy_review_prepare(args: argparse.Namespace) -> int:
    result = prepare_review(corpus_path=Path(args.corpus), taxonomy_path=Path(args.taxonomy), output_dir=Path(args.output), similarities_path=Path(args.similarities) if args.similarities else None, previous_review=Path(args.previous_review) if args.previous_review else None)
    print(f"Prepared deterministic human-governed review {result['review_summary']['review_id']}")
    return 0


def taxonomy_review_validate(args: argparse.Namespace) -> int:
    validate_implemented_change(corpus_path=Path(args.corpus), baseline_taxonomy_path=Path(args.baseline_taxonomy), candidate_taxonomy_path=Path(args.candidate_taxonomy), decision_record_path=Path(args.decision_record), output_path=Path(args.output))
    print("Wrote non-mutating taxonomy implementation validation")
    return 0


def taxonomy_review_model_review(args: argparse.Namespace) -> int:
    result = model_review(review_summary_path=Path(args.review_summary), output_dir=Path(args.output), model=args.model, reasoning_effort=args.reasoning_effort)
    print(f"Wrote advisory-only model review for {result['model_review']['review_id']}")
    return 0


def taxonomy_review_render_decisions(args: argparse.Namespace) -> int:
    decisions = render_decisions(decision_record_path=Path(args.decision_record), output_path=Path(args.output))
    print(f"Rendered {len(decisions)} validated human taxonomy decisions")
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="causebase")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo-build", help="Build the credential-free vertical slice")
    demo.add_argument(
        "--source",
        default="tests/fixtures/source/entities.json",
        help="Fixture source JSON",
    )
    demo.add_argument("--output", default="dist/demo")
    demo.add_argument("--dataset-version", default="demo-0.1")
    demo.add_argument("--registry", help="Governed CauseBase Data subject registry for real-card builds")
    demo.add_argument(
        "--allow-missing-parquet",
        action="store_true",
        help="For constrained test environments only; production publication requires Parquet.",
    )
    demo.set_defaults(func=build_demo)

    val = sub.add_parser("validate", help="Validate an existing publication candidate")
    val.add_argument("--output", default="dist/demo")
    val.set_defaults(func=validate_existing)

    phase2b = sub.add_parser("project-phase2b", help="Create an append-only Phase 2B release from a validated historical release")
    phase2b.add_argument("--input", required=True, help="Historical validated public release directory")
    phase2b.add_argument("--output", required=True, help="New empty candidate directory")
    phase2b.add_argument("--dataset-version", required=True)
    phase2b.add_argument("--archive-root", required=True, help="Private evidence archive required for the RC2 editorial migration")
    phase2b.add_argument("--cache-root", required=True, help="Private content-addressed synthesis cache")
    phase2b.add_argument("--model", default="gpt-5-mini")
    phase2b.set_defaults(func=project_phase2b_release)
    phase2c = sub.add_parser("project-phase2c", help="Create RC4 evidence-driven projection without summary synthesis")
    phase2c.add_argument("--input", required=True); phase2c.add_argument("--output", required=True); phase2c.add_argument("--dataset-version", required=True); phase2c.add_argument("--archive-root", required=True); phase2c.add_argument("--embedding-cache-root")
    phase2c.set_defaults(func=project_phase2c_release)

    paths = sub.add_parser("paths", help="Show configured durable/runtime/public-data paths")
    paths.add_argument("--workspace", default="..", help="CauseBase workspace root")
    paths.set_defaults(func=show_paths)

    golden = sub.add_parser("benchmark-golden", help="Run the private Golden Corpus document-stack benchmark")
    golden.add_argument("--corpus", required=True, help="Versioned public Golden Corpus manifest")
    golden.add_argument("--archive-root", help="Private durable archive root; omitted means document cases are skipped")
    golden.add_argument("--runtime-root", required=True, help="Private mutable directory for caches and reports")
    golden.add_argument("--gold-card", help="Immutable public card used only as output comparison for financial hard gold")
    golden.set_defaults(func=benchmark_golden)

    spike = sub.add_parser("reality-spike-resolve", help="Resolve cohort seeds conservatively")
    spike.add_argument("--cohort", required=True)
    spike.add_argument("--acnc-csv", required=True)
    spike.add_argument("--source-inventory")
    spike.add_argument("--identifier-evidence")
    spike.add_argument("--output", required=True)
    spike.set_defaults(func=resolve_reality_spike)

    report = sub.add_parser("extract-report", help="Extract private PDF evidence for review")
    report.add_argument("--pdf", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--max-pages", type=int)
    report.add_argument("--start-page", type=int, default=1)
    report.set_defaults(func=extract_report)

    ais = sub.add_parser("reality-spike-map-ais", help="Map candidate records to AIS coverage")
    ais.add_argument("--resolution-report", required=True)
    ais.add_argument("--ais-csv", required=True)
    ais.add_argument("--output", required=True)
    ais.set_defaults(func=map_ais)

    web = sub.add_parser("extract-web", help="Extract private readable text from a web snapshot")
    web.add_argument("--html", required=True)
    web.add_argument("--output", required=True)
    web.set_defaults(func=extract_web)

    reports = sub.add_parser("reality-spike-resolve-reports", help="Resolve report ABNs to ACNC records")
    reports.add_argument("--extract", action="append", required=True)
    reports.add_argument("--acnc-csv", required=True)
    reports.add_argument("--source-inventory")
    reports.add_argument("--output", required=True)
    reports.set_defaults(func=resolve_reports)

    promote = sub.add_parser("promote-subject", help="Explicitly mint a durable CauseBase subject ID")
    promote.add_argument("--registry", required=True)
    promote.add_argument("--resolution-report", required=True)
    promote.add_argument("--seed-name", required=True)
    promote.add_argument("--subject-kind", default="organisation")
    promote.add_argument("--display-name")
    promote.set_defaults(func=promote_subject)

    national = sub.add_parser("build-national-backbone", help="Normalise national sources privately and render a safe backbone")
    national.add_argument("--acnc-csv", required=True)
    national.add_argument("--acnc-metadata", required=True)
    national.add_argument("--ais-csv", required=True)
    national.add_argument("--ais-metadata", required=True)
    national.add_argument("--dgr-observations")
    national.add_argument("--dgr-bulk-zip", action="append")
    national.add_argument("--dgr-metadata")
    national.add_argument("--registry", required=True)
    national.add_argument("--private-output", required=True)
    national.add_argument("--public-output", required=True)
    national.set_defaults(func=build_national)

    review = sub.add_parser("taxonomy-review", help="Historical model-led v0.1 review runner; use taxonomy-review-prepare for the durable workflow")
    review.add_argument("--corpus", required=True, help="Private Phase 2A canonical causebase.json")
    review.add_argument("--taxonomy", default="config/taxonomies/causebase-v0.json", help="Frozen baseline taxonomy JSON")
    review.add_argument("--similarities", help="Optional private Phase 2A similarities.json for aggregate diagnostics")
    review.add_argument("--output", required=True, help="Separate private archive directory for review artefacts")
    review.add_argument("--reuse-blind-review", help="Private prior taxonomy-review.json with matching frozen blind input; reruns Pass B and annex only")
    review.add_argument("--model", default="gpt-5-mini", help="Replaceable bounded review model")
    review.set_defaults(func=taxonomy_review)

    prepare = sub.add_parser("taxonomy-review-prepare", help="Prepare a deterministic private human-governed taxonomy review packet")
    prepare.add_argument("--corpus", required=True); prepare.add_argument("--taxonomy", required=True); prepare.add_argument("--output", required=True); prepare.add_argument("--similarities"); prepare.add_argument("--previous-review")
    prepare.set_defaults(func=taxonomy_review_prepare)
    review_validate = sub.add_parser("taxonomy-review-validate", help="Validate an implemented human-approved taxonomy change without mutating data")
    review_validate.add_argument("--corpus", required=True); review_validate.add_argument("--baseline-taxonomy", required=True); review_validate.add_argument("--candidate-taxonomy", required=True); review_validate.add_argument("--decision-record", required=True); review_validate.add_argument("--output", required=True)
    review_validate.set_defaults(func=taxonomy_review_validate)
    model = sub.add_parser("taxonomy-review-model-review", help="Optional advisory model critique of a prepared private packet")
    model.add_argument("--review-summary", required=True); model.add_argument("--output", required=True); model.add_argument("--model", required=True); model.add_argument("--reasoning-effort", default="high")
    model.set_defaults(func=taxonomy_review_model_review)
    decisions = sub.add_parser("taxonomy-review-render-decisions", help="Render validated human decision JSON as Markdown")
    decisions.add_argument("--decision-record", required=True); decisions.add_argument("--output", required=True)
    decisions.set_defaults(func=taxonomy_review_render_decisions)
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

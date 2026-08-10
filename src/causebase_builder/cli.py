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
from .validate import mark_manifest_validated, validate_publication


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


def show_paths(args: argparse.Namespace) -> int:
    paths = load_paths(Path(args.workspace).resolve())
    print(f"archive_root={paths.archive_root}")
    print(f"runtime_root={paths.runtime_root}")
    print(f"data_repository_root={paths.data_repository_root}")
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

    paths = sub.add_parser("paths", help="Show configured durable/runtime/public-data paths")
    paths.add_argument("--workspace", default="..", help="CauseBase workspace root")
    paths.set_defaults(func=show_paths)

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
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

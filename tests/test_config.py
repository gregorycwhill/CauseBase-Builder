from pathlib import Path

from causebase_builder.config import load_paths


def test_paths_keep_durable_archive_separate_from_mutable_runtime(monkeypatch, tmp_path: Path):
    archive = tmp_path / "archive"
    runtime = tmp_path / "runtime"
    data = tmp_path / "CauseBase-Data"
    monkeypatch.setenv("CAUSEBASE_ARCHIVE_ROOT", str(archive))
    monkeypatch.setenv("CAUSEBASE_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("CAUSEBASE_DATA_REPOSITORY", str(data))

    paths = load_paths(tmp_path)

    assert paths.source_archive_root == archive / "sources"
    assert paths.processed_archive_root == archive / "processed"
    assert paths.staging_root == runtime / "staging"
    assert paths.data_repository_root == data

    paths.initialise_runtime()
    assert paths.staging_root.is_dir()
    assert not archive.exists()

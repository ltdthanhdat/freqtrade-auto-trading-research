import json
from pathlib import Path

import pytest

from research_runtime.snapshots import atomic_write_json, directory_sha256, publish_snapshot


def test_directory_hash_is_order_independent(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "b.feather").write_bytes(b"b")
    (dataset / "a.feather").write_bytes(b"a")

    first = directory_sha256(dataset)
    (dataset / "a.feather").touch()

    assert directory_sha256(dataset) == first


def test_publish_snapshot_never_overwrites_existing_final(tmp_path: Path):
    staging = tmp_path / "staging"
    final = tmp_path / "final"
    staging.mkdir()
    (staging / "BTC-1m-futures.feather").write_bytes(b"data")
    final.mkdir()

    with pytest.raises(FileExistsError):
        publish_snapshot(staging, final)


def test_atomic_manifest_has_sealed_status(tmp_path: Path):
    path = tmp_path / "snapshot-readiness.json"
    digest = atomic_write_json(path, {"schema_version": 1, "status": "SEALED"})

    payload = json.loads(path.read_text())
    assert payload["status"] == "SEALED"
    assert len(digest) == 64
    assert not list(tmp_path.glob("*.tmp"))

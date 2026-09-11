import json

from research_runtime.migrate_legacy import import_legacy
from research_runtime.store import ResearchStore


def make_legacy_fixture(tmp_path):
    root = tmp_path / ".research"
    for family, suffix in (("smc", "001"), ("rsi", "002")):
        base = root / family
        (base / "hypotheses").mkdir(parents=True)
        (base / "experiments").mkdir()
        (base / "runs").mkdir()
        (base / "hypotheses" / f"H-{suffix}.md").write_text(
            f"# H-{suffix}\nEvidence body\n", encoding="utf-8"
        )
        (base / "experiments" / f"EXP-{suffix}.md").write_text(
            f"# EXP-{suffix}\nHypothesis: H-{suffix}\n", encoding="utf-8"
        )
        (base / "runs" / f"run-{suffix}.json").write_text(
            '{"verdict":"PASS"}\n', encoding="utf-8"
        )
    return root


def test_importer_preserves_bodies_and_artifact_hashes(tmp_path):
    legacy = make_legacy_fixture(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite")
    report = import_legacy(legacy, store, tmp_path / "artifacts")
    assert report.hypotheses == 2
    assert report.experiments == 2
    assert report.artifacts == 2
    assert report.unresolved_links == ()
    assert report.hash_mismatches == ()
    assert (tmp_path / "artifacts" / "legacy" / "smc" / "runs" / "run-001.json").exists()


def test_importer_is_idempotent_and_keeps_legacy_source(tmp_path):
    legacy = make_legacy_fixture(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite")
    first = import_legacy(legacy, store, tmp_path / "artifacts")
    second = import_legacy(legacy, store, tmp_path / "artifacts")
    assert second == first
    assert (legacy / "smc" / "hypotheses" / "H-001.md").exists()
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0] == 2


def test_unresolved_experiment_link_is_reported_without_deleting_source(tmp_path):
    legacy = make_legacy_fixture(tmp_path)
    (legacy / "smc" / "experiments" / "EXP-001.md").write_text(
        "# EXP-001\nHypothesis: H-MISSING\n", encoding="utf-8"
    )
    store = ResearchStore(tmp_path / "research.sqlite")
    report = import_legacy(legacy, store, tmp_path / "artifacts")
    assert report.unresolved_links
    assert (legacy / "smc" / "experiments" / "EXP-001.md").exists()


def test_verify_report_contains_integrity_and_foreign_key_results(tmp_path):
    legacy = make_legacy_fixture(tmp_path)
    store = ResearchStore(tmp_path / "research.sqlite")
    report = import_legacy(legacy, store, tmp_path / "artifacts")
    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["integrity_check"] == "ok"
    assert payload["foreign_key_errors"] == []

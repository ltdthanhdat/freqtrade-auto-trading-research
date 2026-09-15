from pathlib import Path

import pytest

from research_runtime import paths


def test_default_paths_use_project_namespace(monkeypatch):
    monkeypatch.delenv("RESEARCH_STATE_DIR", raising=False)
    monkeypatch.delenv("RESEARCH_DB", raising=False)
    monkeypatch.delenv("VALIDATION_STATE_DB", raising=False)
    monkeypatch.delenv("RESEARCH_ARTIFACT_ROOT", raising=False)

    assert paths.research_db_path() == Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research/research.sqlite"
    assert paths.validation_state_db_path() == Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research/validation-state.sqlite"
    assert paths.research_artifact_root() == Path("user_data/research-artifacts")


def test_explicit_file_overrides_win(monkeypatch, tmp_path):
    research = tmp_path / "research.sqlite"
    validation = tmp_path / "validation.sqlite"
    monkeypatch.setenv("RESEARCH_DB", str(research))
    monkeypatch.setenv("VALIDATION_STATE_DB", str(validation))

    assert paths.research_db_path() == research
    assert paths.validation_state_db_path() == validation


@pytest.mark.parametrize(
    "name", ["RESEARCH_STATE_DIR", "RESEARCH_DB", "VALIDATION_STATE_DB", "RESEARCH_ARTIFACT_ROOT"]
)
def test_empty_path_override_is_rejected(monkeypatch, name):
    monkeypatch.setenv(name, "")

    with pytest.raises(ValueError, match=name):
        getattr(
            paths,
            {
                "RESEARCH_STATE_DIR": "default_state_dir",
                "RESEARCH_DB": "research_db_path",
                "VALIDATION_STATE_DB": "validation_state_db_path",
                "RESEARCH_ARTIFACT_ROOT": "research_artifact_root",
            }[name],
        )()

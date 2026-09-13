import pytest

from research_runtime.candidates import validate_candidate_source, write_candidate


VALID_STRATEGY = "class CandidateA:\n    pass\n"


def test_candidate_source_policy_requires_concrete_istrategy_for_identity_bound_candidates():
    valid = "from freqtrade.strategy import IStrategy\nclass CandidateA(IStrategy):\n    pass\n"
    module = validate_candidate_source(valid, "CandidateA", identity_bound=True)
    assert module.__class__.__name__ == "Module"

    with pytest.raises(ValueError, match="IStrategy"):
        validate_candidate_source("class CandidateA:\n    pass\n", "CandidateA", identity_bound=True)


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nclass CandidateA: pass\n",
        "import socket\nclass CandidateA: pass\n",
        "import requests\nclass CandidateA: pass\n",
        "import sqlite3\nclass CandidateA: pass\n",
        "import os\nclass CandidateA: pass\n",
        "from pathlib import Path\nclass CandidateA: pass\n",
        "from importlib import import_module\nclass CandidateA: pass\n",
        "class CandidateA:\n    value = eval('1')\n",
        "class CandidateA:\n    value = open('x')\n",
        "class CandidateA:\n    def run(self, connection):\n        connection.execute('SELECT 1')\n",
    ],
)
def test_candidate_source_policy_rejects_unsafe_operations(source):
    with pytest.raises(ValueError, match="candidate policy"):
        validate_candidate_source(source, "CandidateA", identity_bound=False)


def test_candidate_writer_confines_output_and_hashes_source(tmp_path):
    identity = write_candidate(tmp_path, "cycle-1", "CandidateA", VALID_STRATEGY)

    assert identity.path == tmp_path / "cycle-1" / "candidate" / "CandidateA.py"
    assert len(identity.sha256) == 64
    assert identity.path.read_text() == VALID_STRATEGY


def test_candidate_writer_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="strategy name"):
        write_candidate(tmp_path, "cycle-1", "../outside", VALID_STRATEGY)


def test_candidate_writer_rejects_cycle_path_escape(tmp_path):
    with pytest.raises(ValueError, match="cycle path"):
        write_candidate(tmp_path, "../outside", "CandidateA", VALID_STRATEGY)


def test_candidate_writer_rejects_invalid_python(tmp_path):
    with pytest.raises(ValueError, match="syntax"):
        write_candidate(tmp_path, "cycle-1", "Broken", "class :")


def test_candidate_writer_requires_exact_requested_class(tmp_path):
    with pytest.raises(ValueError, match="exactly one class"):
        write_candidate(tmp_path, "cycle-1", "CandidateA", "class Other: pass\n")
    with pytest.raises(ValueError, match="exactly one class"):
        write_candidate(tmp_path, "cycle-1", "CandidateA", "class CandidateA: pass\nclass Helper: pass\n")


def test_candidate_writer_is_idempotent_but_never_overwrites(tmp_path):
    first = write_candidate(tmp_path, "cycle-1", "CandidateA", VALID_STRATEGY)
    assert write_candidate(tmp_path, "cycle-1", "CandidateA", VALID_STRATEGY) == first
    with pytest.raises(ValueError, match="already exists"):
        write_candidate(tmp_path, "cycle-1", "CandidateA", "class CandidateA:\n    changed = True\n")


def test_candidate_writer_allows_only_one_name_per_cycle(tmp_path):
    write_candidate(tmp_path, "cycle-1", "CandidateA", VALID_STRATEGY)
    with pytest.raises(ValueError, match="candidate budget"):
        write_candidate(tmp_path, "cycle-1", "CandidateB", "class CandidateB:\n    pass\n")

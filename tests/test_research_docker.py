from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:|\Z)",
        compose,
    )
    assert match, f"compose service {service!r} is missing"
    return match.group(0)


def test_compose_separates_prep_write_mount_from_research_read_mount() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    prep = compose[compose.index("  research-data-prep:") :]
    research = compose[compose.index("  research:") : compose.index("  research-data-prep:")]

    assert "scripts.prepare_research_data" in prep
    assert "research-data-prep" in compose
    assert "read_only: true" in research
    assert "stdin_open: false" in research
    assert "tty: false" in research
    assert "network_mode: bridge" in research
    assert "./user_data:/" not in research
    assert "CODEX_HOME" not in prep
    assert "PI_AGENT_DIR" not in prep
    assert "RESEARCH_SNAPSHOT_WORK_ROOT" in prep
    assert "RESEARCH_ARTIFACT_ROOT" in prep
    assert "--timeframes" in prep
    assert "30m" in prep and "1h" in prep and "1m" in prep
    assert "--manifest" in prep
    assert "--run-key" in prep
    assert "--summary-root" in prep
    assert "--snapshot-manifest" in research


def test_research_service_is_opt_in_one_shot_and_persists_state() -> None:
    compose_path = ROOT / "compose.yaml"
    assert compose_path.is_file()
    block = _service_block(compose_path.read_text(), "research")

    assert 'profiles: ["research"]' in block
    assert "restart:" not in block
    assert 'entrypoint: ["/usr/local/bin/research-entrypoint"]' in block
    assert "read_only: true" in block
    assert "stdin_open: false" in block
    assert "tty: false" in block
    assert "network_mode: bridge" in block
    assert "uid=1000" in block
    assert "gid=1000" in block
    assert "/home/ftuser/.cache" in block
    assert "\n      - /home/ftuser\n" not in block
    assert "${RESEARCH_ROOT:-/workspace}/user_data" in block
    assert "RESEARCH_ROOT" in block
    assert "RESEARCH_STATE_DIR" in block
    assert "- /state/research" in block
    assert "RESEARCH_ARTIFACT_ROOT" in block
    assert "./user_data:/workspace/user_data" not in block
    assert "- --db" in block
    assert "--max-cycles" in block
    assert "--cycle-timeout" in block
    assert "CODEX_HOME" in block
    assert "- ${CODEX_HOME:-${HOME}/.codex}:/home/ftuser/.codex:ro" in block
    assert "- ${PI_AGENT_DIR:-${HOME}/.pi/agent}:/pi/agent-source:ro" in block
    assert "- ${PI_WEB_SEARCH_CONFIG:-${HOME}/.pi/web-search.json}:/pi/web-search.json:ro" in block
    assert "PI_AGENT_SOURCE_DIR" in block
    assert "PI_CODING_AGENT_DIR" in block
    assert "PI_WEB_SEARCH_CONFIG_SOURCE" in block
    assert "/home/ftuser/.pi" not in block
    assert "/run/research-auth" not in block


def test_research_uses_namespaced_state_and_not_repo_local_database() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    research = compose[compose.index("  research:") :]

    assert "RESEARCH_STATE_DIR" in research
    assert "/state/research" in research
    assert "--db" in research
    assert "/state/research/research.sqlite" in research
    assert "./user_data/research.sqlite" not in research
    assert "./user_data:/" not in research


def test_research_image_contains_pi_and_project_runtime() -> None:
    dockerfile = ROOT / "Dockerfile.research"
    assert dockerfile.is_file()
    content = dockerfile.read_text()

    assert "freqtradeorg/freqtrade:develop" in content
    assert "@earendil-works/pi-coding-agent@0.85.1" in content
    assert "pi-web-access@0.28.0" in content
    assert "PI_WEB_ACCESS_EXTENSION=/opt/pi-extensions/node_modules/pi-web-access/index.ts" in content
    assert "npm ci" in content
    assert "uv" in content
    assert "UV_NO_SYNC" in content
    assert "/opt/research-venv" in content
    assert "UV_PROJECT_ENVIRONMENT=/opt/research-venv" in content
    assert "COPY scripts/research_container_entrypoint.sh /usr/local/bin/research-entrypoint" in content
    assert "ENTRYPOINT [\"/usr/local/bin/research-entrypoint\"]" in content
    assert "mkdir -p /workspace/user_data/data/snapshots /workspace/user_data/research-artifacts" in content


def test_research_entrypoint_uses_disposable_pi_overlay() -> None:
    entrypoint = ROOT / "scripts/research_container_entrypoint.sh"
    assert entrypoint.is_file()
    content = entrypoint.read_text()

    assert "/pi/agent-source" in content
    assert "/pi/web-search.json" in content
    assert "/tmp/pi-agent" in content
    assert "PI_CODING_AGENT_DIR" in content
    assert "cp -R" in content
    assert 'exec /opt/research-venv/bin/python -m scripts.research_loop "$@"' in content


def test_research_dockerignore_excludes_secrets_and_runtime_state() -> None:
    dockerignore = ROOT / ".dockerignore"
    assert dockerignore.is_file()
    content = dockerignore.read_text().splitlines()

    assert ".env" in content
    assert "user_data/" in content
    assert ".git/" in content


def test_makefile_exposes_one_shot_research_container_command() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "compose-research" in makefile
    assert 'RESEARCH_ROOT="$(CURDIR)"' in makefile
    assert "docker compose --profile research run --rm research" in makefile

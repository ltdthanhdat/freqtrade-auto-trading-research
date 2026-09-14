from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re


_TOKEN = re.compile(r"{{[A-Z0-9_]+}}")


def load_research_prompt(path: Path = Path("prompts/strategy-research.md")) -> tuple[str, str]:
    """Read the canonical research prompt and return its raw SHA-256 digest."""
    template = path.read_text(encoding="utf-8")
    return template, sha256(template.encode("utf-8")).hexdigest()


def render_research_prompt(
    template: str, *, cycle_id: str, validation_context: str
) -> str:
    """Render the two runtime-owned prompt values and reject unknown tokens."""
    rendered = template.replace("{{CYCLE_ID}}", cycle_id).replace(
        "{{VALIDATION_CONTEXT}}", validation_context
    )
    unresolved = _TOKEN.findall(rendered)
    if unresolved:
        raise ValueError(f"unresolved prompt token: {unresolved[0]}")
    return rendered

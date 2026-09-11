from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .core import canonical_json


class ProviderError(RuntimeError):
    """A provider rejected or returned an unusable response."""


class ProviderRetryableError(ProviderError):
    """A temporary provider response may succeed on a bounded retry."""


@dataclass(frozen=True)
class SourceRecord:
    provider: str
    title: str
    excerpt: str
    canonical_url: str | None
    doi: str | None
    license: str | None
    retrieved_at: str
    fingerprint: str
    metadata: dict[str, object]


ALLOWED_GITHUB_LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"})


def _normalize_doi(value: object) -> str | None:
    if not value:
        return None
    doi = str(value).strip().lower()
    doi = re.sub(r"^https?://doi\.org/", "", doi)
    doi = re.sub(r"^doi:", "", doi)
    return doi or None


def _strip_markup(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def _abstract_from_inverted(index: object) -> str:
    if not isinstance(index, dict):
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        if isinstance(positions, list):
            words.extend((int(position), str(word)) for position in positions if isinstance(position, int))
    return " ".join(word for _, word in sorted(words))


def _canonical_url(url: object, doi: str | None) -> str | None:
    if doi:
        return f"https://doi.org/{doi}"
    if not url:
        return None
    return str(url).strip().rstrip("/") or None


def _record(
    provider: str,
    *,
    title: object,
    excerpt: object,
    url: object = None,
    doi: object = None,
    license: object = None,
    metadata: dict[str, object] | None = None,
) -> SourceRecord:
    normalized_doi = _normalize_doi(doi)
    normalized_url = _canonical_url(url, normalized_doi)
    normalized_title = _strip_markup(title)
    normalized_excerpt = _strip_markup(excerpt)
    if not normalized_title:
        raise ProviderError(f"{provider} returned a source without a title")
    fingerprint_input = [provider, normalized_doi, normalized_url, normalized_title, normalized_excerpt]
    fingerprint = hashlib.sha256(canonical_json(fingerprint_input).encode()).hexdigest()
    return SourceRecord(
        provider=provider,
        title=normalized_title,
        excerpt=normalized_excerpt,
        canonical_url=normalized_url,
        doi=normalized_doi,
        license=str(license) if license else None,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        fingerprint=fingerprint,
        metadata=metadata or {},
    )


def _request_bytes(url: str, opener=urlopen, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "strategy-research/1.0", **(headers or {})})
    try:
        with opener(request) as response:
            status = getattr(response, "status", 200)
            if status == 429 or status >= 500:
                raise ProviderRetryableError(f"provider HTTP {status}")
            if status >= 400:
                raise ProviderError(f"provider HTTP {status}")
            return response.read()
    except HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise ProviderRetryableError(f"provider HTTP {exc.code}") from exc
        raise ProviderError(f"provider HTTP {exc.code}") from exc
    except (TimeoutError, URLError) as exc:
        raise ProviderRetryableError("provider network failure") from exc


def _json(url: str, opener=urlopen, headers: dict[str, str] | None = None) -> object:
    try:
        return json.loads(_request_bytes(url, opener, headers))
    except json.JSONDecodeError as exc:
        raise ProviderError("provider returned malformed JSON") from exc


def collect_openalex(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.openalex.org/works?" + urlencode({"search": query, "per-page": limit})
    payload = _json(url, opener)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ProviderError("openalex response missing results")
    return [
        _record(
            "openalex",
            title=item.get("title"),
            excerpt=item.get("abstract") or _abstract_from_inverted(item.get("abstract_inverted_index")),
            url=item.get("id"),
            doi=item.get("doi"),
            metadata={"openalex_id": item.get("id")},
        )
        for item in payload["results"][:limit]
        if isinstance(item, dict)
    ]


def collect_semantic_scholar(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(
        {"query": query, "limit": limit, "fields": "title,abstract,url,externalIds,openAccessPdf"}
    )
    payload = _json(url, opener)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderError("semantic scholar response missing data")
    records = []
    for item in payload["data"][:limit]:
        if not isinstance(item, dict):
            continue
        external = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
        records.append(
            _record(
                "semantic_scholar",
                title=item.get("title"),
                excerpt=item.get("abstract"),
                url=item.get("url"),
                doi=external.get("DOI"),
                metadata={"paper_id": item.get("paperId"), "open_access": item.get("openAccessPdf")},
            )
        )
    return records


def collect_core(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.core.ac.uk/v3/search/works?" + urlencode({"q": query, "limit": limit})
    api_key = os.environ.get("CORE_API_KEY")
    payload = _json(url, opener, {"Authorization": f"Bearer {api_key}"} if api_key else None)
    items = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ProviderError("core response missing results")
    return [
        _record(
            "core",
            title=item.get("title"),
            excerpt=item.get("abstract") or item.get("fullText")[:1000] if isinstance(item.get("fullText"), str) else item.get("abstract"),
            url=item.get("downloadUrl") or item.get("source"),
            doi=item.get("doi"),
            metadata={"id": item.get("id"), "full_text_available": bool(item.get("fullText"))},
        )
        for item in items[:limit]
        if isinstance(item, dict)
    ]


def collect_arxiv(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "http://export.arxiv.org/api/query?" + urlencode({"search_query": f"all:{query}", "max_results": limit})
    try:
        root = ElementTree.fromstring(_request_bytes(url, opener))
    except ElementTree.ParseError as exc:
        raise ProviderError("arxiv response was malformed XML") from exc
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    records = []
    for entry in root.findall("atom:entry", namespace)[:limit]:
        link = next((node.get("href") for node in entry.findall("atom:link", namespace) if node.get("rel") in (None, "alternate")), None)
        records.append(
            _record(
                "arxiv",
                title=entry.findtext("atom:title", default="", namespaces=namespace),
                excerpt=entry.findtext("atom:summary", default="", namespaces=namespace),
                url=entry.findtext("atom:id", default=link or "", namespaces=namespace),
                metadata={"pdf_url": next((node.get("href") for node in entry.findall("atom:link", namespace) if node.get("type") == "application/pdf"), None)},
            )
        )
    return records


def collect_crossref(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.crossref.org/works?" + urlencode({"query": query, "rows": limit})
    payload = _json(url, opener)
    items = payload.get("message", {}).get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ProviderError("crossref response missing items")
    return [
        _record(
            "crossref",
            title=(item.get("title") or [""])[0],
            excerpt=item.get("abstract"),
            url=item.get("URL"),
            doi=item.get("DOI"),
            metadata={"published": item.get("published")},
        )
        for item in items[:limit]
        if isinstance(item, dict)
    ]


def collect_github(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.github.com/search/repositories?" + urlencode({"q": query, "per_page": limit})
    token = os.environ.get("GITHUB_TOKEN")
    payload = _json(url, opener, {"Authorization": f"Bearer {token}"} if token else None)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ProviderError("github response missing items")
    records = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        license_data = item.get("license") if isinstance(item.get("license"), dict) else {}
        spdx = license_data.get("spdx_id")
        if spdx not in ALLOWED_GITHUB_LICENSES:
            continue
        records.append(
            _record(
                "github",
                title=item.get("full_name"),
                excerpt=item.get("description"),
                url=item.get("html_url"),
                license=spdx,
                metadata={"default_branch": item.get("default_branch"), "license_spdx": spdx},
            )
        )
    return records


def collect_stackexchange(query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urlencode(
        {"site": "quant", "q": query, "pagesize": limit, "order": "desc", "sort": "relevance", "filter": "withbody"}
    )
    payload = _json(url, opener)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ProviderError("stackexchange response missing items")
    return [
        _record(
            "stackexchange",
            title=item.get("title"),
            excerpt=item.get("body_markdown") or item.get("body") or item.get("excerpt"),
            url=item.get("link"),
            metadata={"falsifier_only": True, "score": item.get("score"), "answer_count": item.get("answer_count")},
        )
        for item in items[:limit]
        if isinstance(item, dict)
    ]


COLLECTORS = {
    "openalex": collect_openalex,
    "semantic_scholar": collect_semantic_scholar,
    "core": collect_core,
    "arxiv": collect_arxiv,
    "crossref": collect_crossref,
    "github": collect_github,
    "stackexchange": collect_stackexchange,
}


def collect_sources(provider: str, query: str, limit: int, opener=urlopen) -> list[SourceRecord]:
    if provider not in COLLECTORS:
        raise ValueError(f"unsupported provider: {provider}")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    return COLLECTORS[provider](query.strip(), limit, opener)

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from research_runtime.collectors import (
    ProviderError,
    ProviderRetryableError,
    collect_arxiv,
    collect_core,
    collect_crossref,
    collect_github,
    collect_openalex,
    collect_semantic_scholar,
    collect_sources,
    collect_stackexchange,
)


class FakeResponse(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def fake_json(payload):
    return lambda _request: FakeResponse(json.dumps(payload).encode())


def test_openalex_result_keeps_canonical_provenance():
    payload = {
        "results": [
            {
                "title": "RSI divergence",
                "doi": "https://doi.org/10.1234/EXAMPLE",
                "id": "https://openalex.org/W1",
                "abstract_inverted_index": {"signal": [0], "works": [1]},
            }
        ]
    }
    records = collect_openalex("RSI divergence", limit=2, opener=fake_json(payload))
    assert records[0].provider == "openalex"
    assert records[0].doi == "10.1234/example"
    assert records[0].canonical_url == "https://doi.org/10.1234/example"
    assert records[0].retrieved_at.endswith("Z")
    assert records[0].fingerprint


def test_arxiv_xml_is_normalized_to_source_record():
    xml = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>
      <entry><id>http://arxiv.org/abs/1234.5678</id><title>RSI divergence</title>
      <summary>Abstract evidence</summary><link href='http://arxiv.org/pdf/1234.5678'/></entry>
    </feed>"""
    records = collect_arxiv("RSI divergence", limit=1, opener=lambda _request: FakeResponse(xml))
    assert records[0].provider == "arxiv"
    assert records[0].canonical_url == "http://arxiv.org/abs/1234.5678"
    assert records[0].excerpt == "Abstract evidence"


def test_github_keeps_only_allowed_spdx_licenses():
    payload = {
        "items": [
            {"full_name": "allowed/repo", "html_url": "https://github.com/allowed/repo", "description": "code", "license": {"spdx_id": "MIT"}},
            {"full_name": "unknown/repo", "html_url": "https://github.com/unknown/repo", "description": "code", "license": None},
        ]
    }
    records = collect_github("RSI", limit=2, opener=fake_json(payload))
    assert [record.title for record in records] == ["allowed/repo"]
    assert records[0].license == "MIT"


def test_semantic_scholar_uses_doi_as_canonical_identity():
    payload = {
        "data": [
            {
                "paperId": "P1",
                "title": "RSI divergence",
                "abstract": "Abstract evidence",
                "url": "https://semanticscholar.org/paper/P1",
                "externalIds": {"DOI": "10.1234/EXAMPLE"},
                "openAccessPdf": {"url": "https://example.test/paper.pdf"},
            }
        ]
    }
    records = collect_semantic_scholar("RSI", limit=1, opener=fake_json(payload))
    assert records[0].provider == "semantic_scholar"
    assert records[0].canonical_url == "https://doi.org/10.1234/example"
    assert records[0].metadata["open_access"]["url"].endswith(".pdf")


def test_core_falls_back_to_a_bounded_full_text_excerpt():
    payload = {
        "results": [
            {
                "id": "C1",
                "title": "CORE paper",
                "fullText": "full text " * 300,
                "downloadUrl": "https://core.ac.uk/download/C1",
            }
        ]
    }
    records = collect_core("RSI", limit=1, opener=fake_json(payload))
    assert len(records[0].excerpt) <= 1000
    assert records[0].metadata["full_text_available"] is True


def test_crossref_normalizes_doi_and_abstract_markup():
    payload = {
        "message": {
            "items": [
                {
                    "title": ["Crossref paper"],
                    "abstract": "<jats:p>Evidence</jats:p>",
                    "DOI": "10.1234/EXAMPLE",
                    "URL": "https://doi.org/10.1234/EXAMPLE",
                }
            ]
        }
    }
    records = collect_crossref("RSI", limit=1, opener=fake_json(payload))
    assert records[0].doi == "10.1234/example"
    assert records[0].canonical_url == "https://doi.org/10.1234/example"
    assert records[0].excerpt == "Evidence"


def test_malformed_json_is_a_provider_error():
    with pytest.raises(ProviderError, match="malformed JSON"):
        collect_openalex("RSI", limit=1, opener=lambda _request: FakeResponse(b"not-json"))


def test_stackexchange_is_marked_falsifier_only():
    payload = {"items": [{"title": "RSI failure modes", "link": "https://quant.stackexchange.com/q/1", "question_score": 4, "body_markdown": "lookahead"}]}
    records = collect_stackexchange("RSI", limit=1, opener=fake_json(payload))
    assert records[0].metadata["falsifier_only"] is True
    assert records[0].canonical_url.endswith("/q/1")


def test_sources_are_deduplicated_by_doi_before_url_and_fingerprint():
    payload = {
        "results": [
            {"title": "A", "doi": "10.1234/same", "id": "https://openalex.org/1"},
            {"title": "B", "doi": "https://doi.org/10.1234/SAME", "id": "https://openalex.org/2"},
        ]
    }
    records = collect_openalex("same", limit=2, opener=fake_json(payload))
    assert records[0].doi == records[1].doi
    assert records[0].canonical_url == records[1].canonical_url


def test_tradingview_is_not_a_provider():
    with pytest.raises(ValueError, match="unsupported provider"):
        collect_sources("tradingview", "RSI", 10)


def test_http_429_is_retryable():
    def opener(request):
        raise HTTPError(request.full_url, 429, "rate limited", {}, BytesIO())

    with pytest.raises(ProviderRetryableError):
        collect_openalex("RSI", limit=1, opener=opener)


def test_http_403_is_provider_failure():
    def opener(request):
        raise HTTPError(request.full_url, 403, "forbidden", {}, BytesIO())

    with pytest.raises(ProviderError):
        collect_openalex("RSI", limit=1, opener=opener)

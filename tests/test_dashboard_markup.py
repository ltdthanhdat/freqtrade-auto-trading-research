import re
from pathlib import Path


HTML = Path("dashboard/index.html").read_text()


def test_dashboard_has_five_named_views_and_no_trading_controls():
    assert set(re.findall(r'data-view="([^"]+)"', HTML)) == {
        "overview", "sources", "hypotheses", "experiments", "review"
    }
    assert "Sample data" not in HTML
    assert not re.search(r">\s*(Start dry-run|Start live|Run cycle)\s*<", HTML, re.I)


def test_review_controls_require_reason_and_confirmation():
    assert 'id="reviewReason"' in HTML
    assert "window.confirm" in HTML
    assert 'Content-Type": "application/json"' in HTML


def test_dashboard_has_accessible_live_states_tables_and_same_origin_assets():
    assert HTML.count('src="/assets/plotly.min.js"') == 1
    assert not re.search(r"https?://", HTML)
    ids = re.findall(r'id="([^"]+)"', HTML)
    assert len(ids) == len(set(ids))
    assert "prefers-reduced-motion" in HTML
    assert "<caption" in HTML and "aria-live" in HTML
    assert 'id="loading"' in HTML and 'id="error"' in HTML
    assert 'id="chart-title"' in HTML and 'id="chart-desc"' in HTML
    assert not re.search(r"\bon(?:click|change|submit)\s*=", HTML, re.I)
    assert "innerHTML" not in HTML
    assert "textContent" in HTML
    assert "Plotly.newPlot" in HTML
    assert 'id="foldTable"' in HTML

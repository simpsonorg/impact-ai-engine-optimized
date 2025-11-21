import json
from unittest.mock import patch
from analyzer.impact_analyzer import analyze


def test_llm_parsing_and_fallback(monkeypatch):
    # create a canned structured response
    canned = {
        "brief_summary": "Test summary",
        "overall_risk": "low",
        "confidence": 0.9,
        "impact_by_service": [],
        "recommended_next_steps": [],
        "markdown_comment": "<div>Fake PR Comment</div>"
    }
    assistant_text = json.dumps(canned) + "\n" + canned['markdown_comment']

    # monkeypatch the _call_llm_messages function to return this text
    monkeypatch.setattr('analyzer.impact_analyzer._call_llm_messages', lambda messages: assistant_text)

    out = analyze("(no PR title)", ["svc-a/app.py"], ["svc-a"], {"nodes": [], "edges": []}, [])
    assert "Fake PR Comment" in out

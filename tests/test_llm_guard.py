"""The number check that stops the LLM from inventing figures."""

from unittest.mock import patch

from app import llm


def allowed_from(*values):
    out = set()
    llm._collect_numbers(list(values), out)
    return out


def test_numbers_from_evidence_pass_at_their_written_precision():
    allowed = allowed_from(9.42, 3.79, 2.5, 141796)
    assert llm.unsupported_numbers("Reels hit 9.42% vs 3.79% (2.5x), reach 141,796.", allowed) == []
    assert llm.unsupported_numbers("Reels hit about 9.4%.", allowed) == []


def test_invented_numbers_are_caught():
    allowed = allowed_from(9.42, 3.79)
    assert llm.unsupported_numbers("Engagement jumped 37% thanks to reels.", allowed) == ["37"]


def test_unknown_post_ids_are_caught():
    assert llm.unknown_post_ids("See AM-0038 and BC-0012.", {"AM-0038"}) == ["BC-0012"]


def test_bad_llm_sentence_falls_back_to_template(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    findings = [{
        "id": "format_gap", "title": "t", "text": "Reels 9.42% vs photos 3.79%.", "recommendation": "r",
        "evidence": {"metric": "er", "values": {"reel": 9.42, "photo": 3.79}, "sample": {}, "post_ids": ["AM-0001"]},
    }]
    metrics = {"period": "2026-10", "previous_period": "2026-09",
               "totals": {"posts": 30, "reach": 1000, "engagement_rate": 5.0}}
    fake = {"summary": "Great month with 30 posts.",
            "insights": [{"id": "format_gap", "text": "Reels did 48% better.", "recommendation": "More reels."}]}

    with patch.object(llm, "_call_claude", return_value=(fake, "fake-model")):
        summary, accepted, info = llm.phrase_findings("Hotel", metrics, findings)

    assert summary == "Great month with 30 posts."
    assert accepted == {}  # "48%" isn't in the evidence -> rejected
    assert info["rejected"][0]["unsupported"] == ["48"]

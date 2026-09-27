from __future__ import annotations

import pytest

from pipeline.studio import handoff
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import claims, numbering
from pipeline.studio.paper.workspace import parse_dossier, write_json
from tests.pipeline.studio import fixtures as fx


def _answer(row, verdict="supported", quote=None, qsid=None):
    answer = fx.claim_answers([row], verdict)[0]
    if quote is not None:
        answer["quote"], answer["quote_source_id"] = quote, qsid
    return answer


def test_export_builds_evidence_paragraph_and_coherence_tasks(tmp_path):
    ws = fx.make_workspace(tmp_path)
    counts = claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    kinds = [r["kind"] for r in rows]
    assert kinds.count("evidence") == 2
    assert kinds.count("coherence") == 1
    assert kinds.count("paragraph") == len(rows) - 3
    assert counts == {"tasks": len(rows), "pending": len(rows), "accepted": 0}
    ev = rows[0]
    assert ev["ref"] == "ev-01"
    assert ev["cited"] == [
        {
            "source_id": fx.S1,
            "url": "https://www.dainst.org/baalbek-report",
            "title": "Baalbek quarry excavation report",
            "text_path": f"texts/{fx.S1}.txt",
            "text_status": "full_text",
        }
    ]
    prompt = (ws.claims_dir / ev["prompt_path"]).read_text(encoding="utf-8")
    assert prompt.startswith("IMPORTANT:")
    assert '"claim": "The Stone of the Pregnant Woman weighs about 1000 tons."' in prompt


def test_export_refuses_invalid_evidence(tmp_path):
    ws = fx.make_workspace(tmp_path)
    bad = [dict(fx.EVIDENCE[0], quote="not in the source at all")]
    write_json(ws.evidence, bad)
    with pytest.raises(StudioError, match="evidence.json: .*does not occur verbatim"):
        claims.export_claims(ws)


def test_import_machine_checks_supported_quotes(tmp_path):
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    bad = _answer(rows[0], quote="The Stone weighs 5000 t.", qsid=fx.S1)
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", [bad])
    with pytest.raises(handoff.HandoffError, match="quote does not occur verbatim"):
        claims.import_claims(ws)
    wrong_source = _answer(rows[0], quote="Baalbek is a city in the Beqaa Valley.", qsid=fx.S2)
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", [wrong_source])
    with pytest.raises(handoff.HandoffError, match="not one of the task's cited sources"):
        claims.import_claims(ws)
    unchallenged = dict(_answer(rows[0]), skeptic_by=" ")
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", [unchallenged])
    with pytest.raises(handoff.HandoffError, match="supported needs the skeptic's confirmation"):
        claims.import_claims(ws)


def test_import_reports_the_tasks_still_unanswered(tmp_path):
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", [_answer(rows[0])])
    with pytest.raises(StudioError, match=rf"^{len(rows) - 1} claim tasks have no accepted"):
        claims.import_claims(ws)
    assert list(handoff.load_accepted(ws.claims_dir)) == [rows[0]["task_id"]]


def test_claim_status_passes_only_when_every_task_is_supported(tmp_path):
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    answers = [_answer(r) for r in rows]
    answers[-1] = _answer(rows[-1], verdict="unsupported")  # the coherence task
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", answers)
    assert claims.import_claims(ws) == {"accepted": len(rows)}
    built = numbering.build_paper(ws)
    dossier = parse_dossier(fx.dossier_gz_bytes())
    status = claims.claim_status(ws, built, dossier, fx.EVIDENCE)
    assert not status.passed
    assert status.missing == []
    assert status.coherence_conflicts == 1
    assert status.not_supported[0]["ref"] == "coherence:numbers"


def test_a_changed_paragraph_becomes_a_new_pending_task(tmp_path):
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", [_answer(r) for r in rows])
    claims.import_claims(ws)
    draft = ws.draft.read_text(encoding="utf-8").replace(
        "It still lies in the Baalbek quarry [S:aaaaaaaaaaa1].",
        "It still lies in the Baalbek quarry today [S:aaaaaaaaaaa1].",
    )
    ws.draft.write_text(draft, encoding="utf-8")
    counts = claims.export_claims(ws)
    assert counts["pending"] == 2  # ev-01 and the paragraph task of its paragraph
    status = claims.claim_status(
        ws, numbering.build_paper(ws), parse_dossier(fx.dossier_gz_bytes()), fx.EVIDENCE
    )
    assert sorted(status.missing) == ["evidence:ev-01", "paragraph:p2"]


LIVE_QUOTE = "Roman engineers moved the largest blocks on sledges."
TDM_URL = "https://publisher.example/paywalled"


def _tdm_workspace(tmp_path):
    """The fixture paper with one paragraph that also cites the TDM-reserved S4."""
    draft = fx.build_draft().replace(
        "It is likely that Roman engineers moved the blocks [S:aaaaaaaaaaa1].",
        f"It is likely that Roman engineers moved the blocks [S:aaaaaaaaaaa1] [S:{fx.S4}].",
    )
    ws = fx.make_workspace(tmp_path, draft=draft)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    row = next(r for r in rows if any(c["source_id"] == fx.S4 for c in r["cited"]))
    return ws, row


def _live(ws, body=LIVE_QUOTE, url=TDM_URL, fetched="2026-09-26T21:00:00Z"):
    path = ws.claims_dir / "live" / f"{fx.S4}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"URL: {url}\nFetched: {fetched}\n\n{body}\n", encoding="utf-8")


def test_a_tdm_reserved_source_is_read_live_and_its_quote_machine_checked(tmp_path):
    ws, row = _tdm_workspace(tmp_path)
    assert [c for c in row["cited"] if c["source_id"] == fx.S4] == [
        {
            "source_id": fx.S4,
            "url": TDM_URL,
            "title": "Paywalled monograph",
            "text_path": None,
            "text_status": "tdm_reserved",
        }
    ]
    prompt = (ws.claims_dir / row["prompt_path"]).read_text(encoding="utf-8")
    assert "save the exact text you read to `claims_check/live/<source_id>.txt`" in prompt
    handoff.write_jsonl(
        ws.claims_dir / "verdicts.jsonl", [_answer(row, quote=LIVE_QUOTE, qsid=fx.S4)]
    )
    with pytest.raises(handoff.HandoffError, match=f"claims_check/live/{fx.S4}.txt does not"):
        claims.import_claims(ws)
    _live(ws, url="https://elsewhere.example/")
    with pytest.raises(handoff.HandoffError, match=f"must start with 'URL: {TDM_URL}'"):
        claims.import_claims(ws)
    _live(ws, fetched="2026-09-26T23:00:00+02:00")
    with pytest.raises(handoff.HandoffError, match="must be an ISO-8601 time in UTC"):
        claims.import_claims(ws)
    _live(ws, body="Another page altogether.")
    with pytest.raises(handoff.HandoffError, match=f"verbatim in claims_check/live/{fx.S4}.txt"):
        claims.import_claims(ws)
    _live(ws)
    with pytest.raises(StudioError, match="claim tasks have no accepted answer"):
        claims.import_claims(ws)
    assert row["task_id"] in handoff.load_accepted(ws.claims_dir)


def test_source_texts_add_the_live_text_of_a_tdm_reserved_source(tmp_path):
    ws, _row = _tdm_workspace(tmp_path)
    dossier = parse_dossier(fx.dossier_gz_bytes())
    assert claims.source_texts(ws, dossier) == dossier.texts
    _live(ws)
    texts = claims.source_texts(ws, dossier)
    assert texts[fx.S4] == LIVE_QUOTE + "\n"
    assert {k: v for k, v in texts.items() if k != fx.S4} == dossier.texts

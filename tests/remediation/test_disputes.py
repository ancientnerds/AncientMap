"""Lane E's dispute screen (owner decisions D21 of 2026-10-08 and D50 of 2026-10-19,
`scripts/remediation/wc/disputes.py`): the candidates in code, the categories, the research and the
adjudication with their roles and quote checks, and the two outputs - the briefs an enrichment appends
both positions from and the defect lines a `wc-list` pass reads as a reported claim. Nothing here calls a
model, opens a socket or touches a database. The mutation cases are `ENRICH_MUTATIONS`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import roles as RO  # noqa: E402 - scripts/remediation is on sys.path by wc_fixtures
from phase3.run import read_jsonl  # noqa: E402
from wc import answers as A  # noqa: E402
from wc import cli  # noqa: E402
from wc import disputes as D  # noqa: E402
from wc import enrich as E  # noqa: E402

from tests.remediation import enrich_fixtures as EF
from tests.remediation import wc_fixtures as FX
from tests.remediation import wn_fixtures as WX
from tests.remediation.wc_fixtures import OH, WC4, M

WIKI_TEXT_NEUTRAL = "The temples are a complex of four buildings on Malta."
WIKI_TEXT_FRINGE = (
    "The site is the subject of a controversy. Some authors allege that a lost civilisation built "
    "it, and the claim is disputed by archaeologists. The dating is debated."
)


def _row(site_id: str, description: str, *, site_type: str = "Temple complex", **kw: Any) -> dict:
    return {**FX.row(site_id, description, raw_data=WX.p4_site_raw(), **kw), "site_type": site_type}


# ------------------------------------------------------------------------------ the screen
@pytest.mark.parametrize(
    ("description", "signal"),
    [
        ("A controversial site in New Hampshire, formerly known as Mystery Hill.", "disputed"),
        ("The inscription is considered a hoax by most scholars.", "hoax"),
        ("Some researchers claim the structure is a pyramid built by a lost people.", "claimed"),
        ("It is a rock of likely natural origin that esoteric writers have claimed for ritual use.", "natural"),
        ("The authenticity of the find remains uncertain.", "doubt"),
        ("A pseudoarchaeology favourite on the island.", "pseudo"),
    ],
)  # fmt: skip
def test_the_description_signals_catch_a_text_that_names_a_dispute(
    description: str, signal: str
) -> None:
    row = _row(FX.SITE_A, description)
    reasons = D.candidate_reasons(row, wikipedia=None, categories=(), wiki_min_hits=2)
    assert signal in reasons["description"], reasons


def test_a_plain_description_is_no_candidate() -> None:
    row = _row(FX.SITE_A, "The Tarxien Temples are a complex of four buildings in Tarxien, Malta.")
    assert (
        D.candidate_reasons(row, wikipedia=WIKI_TEXT_NEUTRAL, categories=(), wiki_min_hits=2) == {}
    )


def test_the_wikipedia_text_flags_a_site_from_two_hits_and_the_categories_from_one() -> None:
    row = _row(FX.SITE_A, "A complex in Malta.")
    one = "The dating is debated by scholars of the period."
    assert "wikipedia" not in D.candidate_reasons(
        row, wikipedia=one, categories=(), wiki_min_hits=2
    )
    assert "wikipedia" in D.candidate_reasons(
        row, wikipedia=WIKI_TEXT_FRINGE, categories=(), wiki_min_hits=2
    )
    assert "wikipedia" in D.candidate_reasons(row, wikipedia=one, categories=(), wiki_min_hits=1)
    cats = [
        "Category:Pseudoarchaeology",
        "Category:Rock formations of Wales",
        "Category:Ruins in Peru",
    ]
    assert D.candidate_reasons(row, wikipedia=None, categories=cats, wiki_min_hits=2)["category"] == [
        "pseudoarchaeology", "rock-formations",
    ]  # fmt: skip
    for category, name in (
        ("Category:Archaeological controversies", "controversies"),
        ("Category:North American runestone hoaxes", "hoaxes"),
        ("Category:Lost City of Z", "lost-city"),
        ("Category:Esoteric anthropogenesis", "fringe"),
    ):
        assert (
            name
            in D.candidate_reasons(row, wikipedia=None, categories=[category], wiki_min_hits=2)[
                "category"
            ]
        )
    assert (
        D.candidate_reasons(
            row, wikipedia=None, categories=["Category:Ruins in Peru"], wiki_min_hits=2
        )
        == {}
    )


def test_a_site_type_that_names_an_anomaly_flags_the_site() -> None:
    row = _row(FX.SITE_A, "A feature on the seabed.", site_type="Magnetic anomaly")
    assert D.candidate_reasons(row, wikipedia=None, categories=(), wiki_min_hits=2) == {
        "site_type": ["anomaly"]
    }


def _run(tmp_path: Path, rows: list[dict]) -> Path:
    run = tmp_path / "runs" / "disputes"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    return run


def _cache(tmp_path: Path, texts: dict[str, str]) -> Path:
    cache = tmp_path / "wiki_cache"
    (cache / "en").mkdir(parents=True)
    index = []
    for n, (site_id, text) in enumerate(texts.items()):
        name = f"en/{n}.json"
        (cache / "en" / f"{n}.json").write_text(
            json.dumps({"resolved_title": "T", "revid": 1, "text": text}), encoding="utf-8"
        )
        index.append(
            {"site_id": site_id, "lang": "en", "title": "T", "file": name.replace("/", "\\")}
        )
    (cache / "INDEX.jsonl").write_text(
        "".join(json.dumps(i) + "\n" for i in index), encoding="utf-8"
    )
    return cache


def test_the_candidates_are_the_shown_sites_that_carry_a_signal(tmp_path: Path) -> None:
    rows = [
        _row(FX.SITE_A, "A controversial site in Malta. It has four buildings in the south."),
        _row(FX.SITE_B, "A plain site in Malta with four buildings in the south of the island."),
        _row(FX.SITE_C, "A site that a file calls disputed.", scope_status="retired"),
        _row(FX.SITE_D, "A complex in Malta."),
        {**FX.row(EF.SITE_NONE, None), "site_type": "x"},
    ]
    run = _run(tmp_path, rows)
    (run / D.CATEGORIES_FILE).write_text(
        json.dumps({FX.SITE_D: ["Category:Pseudoarchaeology"]}), encoding="utf-8"
    )
    cache = _cache(tmp_path, {FX.SITE_B: WIKI_TEXT_FRINGE})
    summary = D.cmd_candidates(run, wiki_cache=cache)
    assert summary["candidates"] == 3 and summary["listed"] == {"no-description": 1, "retired": 1}
    assert summary["by_signal"] == {"category": 1, "description": 1, "wikipedia": 1}
    found = {c["site_id"]: c for c in read_jsonl(run / D.CANDIDATES_FILE)}
    assert set(found) == {FX.SITE_A, FX.SITE_B, FX.SITE_D}
    assert found[FX.SITE_A]["sentences"][0].startswith("A controversial site")
    assert found[FX.SITE_A]["desc_sha256"] == M.text_sha256(rows[0]["description"])


def test_the_screen_is_measured_against_the_known_positives(tmp_path: Path) -> None:
    rows = [_row(f"{n:08x}-0000-4000-8000-000000000001", "A controversial hoax.", name=name)
            for n, name in enumerate(D.KNOWN_POSITIVES, start=1)]  # fmt: skip
    run = _run(tmp_path, rows)
    D.cmd_candidates(run, wiki_cache=None)
    assert D.cmd_recall(run) == {
        "known": 17, "flagged": 17, "recall": 1.0, "missed": [], "named": [], "passed": True,
    }  # fmt: skip
    plain = [{**r, "description": "A plain site in Malta with four buildings."} for r in rows[:3]]
    run2 = _run(tmp_path / "b", [*plain, *rows[3:]])
    D.cmd_candidates(run2, wiki_cache=None)
    result = D.cmd_recall(run2)
    assert result["flagged"] == 14 and result["passed"] is False and len(result["missed"]) == 3


def test_the_d50_sites_are_known_positives_and_screened_although_retired(
    tmp_path: Path,
) -> None:
    """D50 (owner, 2026-10-19) supersedes X2: the six retired mystery sites return as disputed
    sites, so the screen asks them; every other retired site stays out."""
    from mechanical.lane import D50_DISPUTED_SITES

    assert set(D50_DISPUTED_SITES.values()) <= set(D.KNOWN_POSITIVES)
    assert len(D50_DISPUTED_SITES) == 6
    (yonaguni,) = [sid for sid, name in D50_DISPUTED_SITES.items() if name == "Yonaguni Monument"]
    rows = [
        _row(yonaguni, "A so-called monument, a natural formation.", scope_status="retired"),
        _row(FX.SITE_C, "A site that a file calls disputed.", scope_status="retired"),
    ]
    run = _run(tmp_path, rows)
    summary = D.cmd_candidates(run, wiki_cache=None)
    assert summary["candidates"] == 1 and summary["listed"] == {"retired": 1}
    assert [c["site_id"] for c in read_jsonl(run / D.CANDIDATES_FILE)] == [yonaguni]
    assert D.screened({"id": yonaguni, "scope_status": "retired"})
    assert not D.screened({"id": FX.SITE_C, "scope_status": "retired"})
    assert D.screened({"id": FX.SITE_C, "scope_status": None})


PLAIN = "A plain site in Malta with four buildings in the south of the island."


def _include(tmp_path: Path, *site_ids: str) -> Path:
    path = tmp_path / "dispute-include.txt"
    path.write_text("".join(f"{site_id}\n" for site_id in site_ids), encoding="utf-8")
    return path


def test_a_named_site_is_a_candidate_whatever_it_carries(tmp_path: Path) -> None:
    """D21 names Pantelleria Vecchia Bank Megalith, whose description, article and categories carry
    no signal: `candidates --include` asks a named site all the same, like any other candidate."""
    rows = [
        _row(FX.SITE_A, "A controversial site in Malta. It has four buildings in the south."),
        _row(FX.SITE_B, PLAIN, name="Pantelleria Vecchia Bank Megalith"),
        _row(FX.SITE_D, PLAIN, name="Unnamed and plain"),
    ]
    run = _run(tmp_path, rows)
    assert D.cmd_candidates(run, wiki_cache=None)["candidates"] == 1  # the screen alone: SITE_A
    include = _include(tmp_path, FX.SITE_A, FX.SITE_B)
    summary = D.cmd_candidates(run, wiki_cache=None, include=include)
    assert summary["candidates"] == 2 and summary["by_signal"] == {"description": 1, "named": 2}
    assert summary["include"] == {
        "path": cli._shown(include), "sha256": cli._sha256(include), "sites": 2,
    }  # fmt: skip
    found = {c["site_id"]: c for c in read_jsonl(run / D.CANDIDATES_FILE)}
    assert set(found) == {FX.SITE_A, FX.SITE_B}
    assert found[FX.SITE_B]["reasons"] == {"named": ["dispute-include.txt"]}
    assert found[FX.SITE_A]["reasons"] == {
        "description": ["disputed"],
        "named": ["dispute-include.txt"],
    }
    assert found[FX.SITE_B]["sentences"] == [PLAIN]
    # the research round asks it exactly as it asks a flagged site
    assert D.cmd_export(run, tmp_path / "h") == {"questions": 2, "batches": 1}
    prompts = {
        m["label"]: (tmp_path / "h" / m["prompt_path"]).read_text(encoding="utf-8")
        for m in OH.manifest(tmp_path / "h")
    }
    assert "name: Pantelleria Vecchia Bank Megalith" in prompts[FX.SITE_B]
    assert "named" not in prompts[FX.SITE_B] and f"S1: {PLAIN}" in prompts[FX.SITE_B]


def test_a_site_asked_by_name_is_no_hit_of_the_screen(tmp_path: Path) -> None:
    """The recall measures the signals: a known positive that is a candidate only because the list
    names it stays among the missed (and is listed as named), so a list never passes the screen."""
    rows = [_row(f"{n:08x}-0000-4000-8000-000000000001", "A controversial hoax.", name=name)
            for n, name in enumerate(D.KNOWN_POSITIVES, start=1)]  # fmt: skip
    plain = [_row(r["id"], PLAIN, name=r["name"]) for r in rows[:3]]
    run = _run(tmp_path, [*plain, *rows[3:]])
    include = _include(tmp_path, *(r["id"] for r in plain[:2]))
    assert D.cmd_candidates(run, wiki_cache=None, include=include)["candidates"] == 16
    result = D.cmd_recall(run)
    assert result["flagged"] == 14 and result["recall"] == round(14 / 17, 4)
    assert result["passed"] is False
    assert result["missed"] == list(D.KNOWN_POSITIVES[:3])
    assert result["named"] == list(D.KNOWN_POSITIVES[:2])


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (_row(FX.SITE_C, "A site that a file calls disputed.", scope_status="retired"), "retired"),
        ({**FX.row(FX.SITE_C, None), "site_type": "x"}, "no-description"),
        (_row(FX.SITE_C, "A disputed site [1-3]. It stands in Malta."), "not-splittable"),
    ],
)
def test_a_named_site_the_screen_cannot_ask_stops_the_command(
    tmp_path: Path, row: dict, reason: str
) -> None:
    """A site the list names is asked or the command stops: it is never left out silently."""
    run = _run(tmp_path, [_row(FX.SITE_A, PLAIN), row])
    # without the list the site is counted under its reason, as before
    assert D.cmd_candidates(run, wiki_cache=None)["listed"] == {reason: 1}
    (run / D.CANDIDATES_FILE).unlink()
    with pytest.raises(D.DisputeError, match=rf"cannot be asked \({reason}\)"):
        D.cmd_candidates(run, wiki_cache=None, include=_include(tmp_path, FX.SITE_C))
    assert not (run / D.CANDIDATES_FILE).exists()
    with pytest.raises(D.DisputeError, match="is no curated row of the read"):
        D.cmd_candidates(run, wiki_cache=None, include=_include(tmp_path, FX.SITE_D))
    bad = tmp_path / "bad.txt"
    bad.write_text("not-a-site-id\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="bad.txt:1"):
        D.cmd_candidates(run, wiki_cache=None, include=bad)


# ------------------------------------------------------------------------------ the categories
def _api(pages: dict[str, list[str]], *, redirects=None, normalized=None, missing=(), split=False):
    """A MediaWiki `prop=categories` answer over a dict; `split` answers in two continued pieces."""
    calls: list[dict] = []

    def get(params: dict) -> dict:
        calls.append(dict(params))
        titles = params["titles"].split("|")
        resolved = []
        for t in titles:
            t = (normalized or {}).get(t, t)
            resolved.append((redirects or {}).get(t, t))
        items = []
        for t in resolved:
            item: dict = {"title": t}
            if t in missing:
                item["missing"] = True
            else:
                cats = pages.get(t, [])
                if split and "clcontinue" not in params:
                    cats = cats[:1]
                elif split:
                    cats = cats[1:]
                if cats:
                    item["categories"] = [{"title": c} for c in cats]
            items.append(item)
        data: dict = {"batchcomplete": True, "query": {"pages": items}}
        if normalized:
            data["query"]["normalized"] = [
                {"from": f, "to": t} for f, t in normalized.items() if f in titles
            ]
        if redirects:
            data["query"]["redirects"] = [
                {"from": f, "to": t}
                for f, t in redirects.items()
                if (normalized or {}).get(f, f) in resolved or f in titles
            ]
        if split and "clcontinue" not in params:
            data = {"continue": {"clcontinue": "1|x", "continue": "||"}, **data}
        return data

    return get, calls


def test_the_categories_of_each_article_are_read_with_redirects_and_continuations() -> None:
    pages = {
        "Gunung Padang": ["Category:Archaeological controversies", "Category:Megalithic monuments"],
        "Dighton Rock": ["Category:North American runestone hoaxes"],
        "Plain": [],
    }
    get, calls = _api(pages, redirects={"Gunung Padang Megalithic Site": "Gunung Padang"},
                      normalized={"dighton rock": "Dighton Rock"})  # fmt: skip
    titles = {"s1": "Gunung Padang Megalithic Site", "s2": "dighton rock", "s3": "Plain"}
    found = D.fetch_categories(titles, get=get)
    assert found == {
        "s1": ["Category:Archaeological controversies", "Category:Megalithic monuments"],
        "s2": ["Category:North American runestone hoaxes"],
        "s3": [],
    }
    assert len(calls) == 1 and calls[0]["redirects"] == 1 and calls[0]["clshow"] == "!hidden"
    get2, calls2 = _api(pages, split=True)
    both = D.fetch_categories({"s1": "Gunung Padang"}, get=get2)
    assert (
        both["s1"] == pages["Gunung Padang"] and len(calls2) == 2
    )  # the continuation was answered


def test_fifty_titles_go_to_one_query_and_a_missing_article_is_an_error() -> None:
    titles = {f"s{n}": f"Article {n}" for n in range(120)}
    get, calls = _api({})
    D.fetch_categories(titles, get=get)
    assert [len(c["titles"].split("|")) for c in calls] == [50, 50, 20]
    missing, _ = _api({}, missing={"Gone"})
    with pytest.raises(D.DisputeError, match="does not exist"):
        D.fetch_categories({"s": "Gone"}, get=missing)


def test_the_categories_file_covers_the_shown_sites_with_a_wikipedia_title(tmp_path: Path) -> None:
    from mechanical.lane import D50_DISPUTED_SITES

    richat = next(s for s, n in D50_DISPUTED_SITES.items() if n == "Richat Structure")
    rows = [
        _row(FX.SITE_A, "A.", name="A"),
        {**_row(FX.SITE_B, "B."), "enwiki_title": None},
        {**_row(FX.SITE_C, "C.", scope_status="retired")},
        {**_row(richat, "R.", scope_status="retired"), "enwiki_title": "Richat Structure"},
    ]
    run = _run(tmp_path, rows)
    get, calls = _api({"Tarxien Temples": ["Category:Rock formations of Wales"]})
    summary = D.cmd_fetch_categories(run, get=get)
    assert summary == {"sites": 2, "with_categories": 1}, "a D50 site is read, SITE_C not"
    assert {t for c in calls for t in c["titles"].split("|")} == {
        "Tarxien Temples",
        "Richat Structure",
    }
    assert json.loads((run / D.CATEGORIES_FILE).read_text(encoding="utf-8")) == {
        FX.SITE_A: ["Category:Rock formations of Wales"],
        richat: [],
    }


# ------------------------------------------------------------------------------ the answers
def _position(url: str = EF.POSITIONS, quote: dict | None = None, **kw: Any) -> dict:
    q = quote or EF.Q_A
    return {"claim": "The first phase is near 3600 BC", "holders": "the excavators",
            "sources": [{"url": url, "title": q["title"], "quote": q["quote"]}], **kw}  # fmt: skip


def _research_answer(site_id: str, **change: Any) -> str:
    data = {
        "site_id": site_id, "disputed": True, "position_a": _position(),
        "position_b": {**_position(quote=EF.Q_B), "claim": "The first phase is near 3150 BC",
                       "holders": "radiocarbon specialists"},
        "asserting": [{"sentence": 2, "asserts": "b"}], "note": "a published controversy",
    }  # fmt: skip
    return json.dumps({**data, **change})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"disputed": "yes"}, "disputed is true or false"),
        ({"position_a": None}, "position_a is not"),
        ({"position_b": {**_position(), "claim": ""}}, "position_b.claim"),
        ({"position_a": {**_position(), "holders": "h" * 301}}, "position_a.holders"),
        ({"position_a": {**_position(), "sources": []}}, "1 to 4"),
        ({"position_a": {**_position(), "sources": _position()["sources"] * 5}}, "quotes, at most"),
        ({"position_a": {**_position(), "sources": [{"url": "x", "title": "t", "quote": "q" * 30}]}},
         "not an http"),
        ({"asserting": [{"sentence": 9, "asserts": "a"}]}, "asserting names"),
        ({"asserting": [{"sentence": 2, "asserts": "c"}]}, "asserting names"),
        ({"asserting": [{"sentence": 1, "asserts": "a"}, {"sentence": 1, "asserts": "b"}]},
         "listed twice"),
        ({"note": ""}, "note"),
    ],
)  # fmt: skip
def test_a_research_answer_the_rules_refuse(change: dict, message: str) -> None:
    with pytest.raises(A.AnswerError, match=message):
        D.parse_research(_research_answer(EF.SITE_W, **change), site_id=EF.SITE_W, sentences=3)


def test_a_research_answer_is_a_dispute_with_two_positions_or_none() -> None:
    parsed = D.parse_research(_research_answer(EF.SITE_W), site_id=EF.SITE_W, sentences=3)
    assert parsed["disputed"] is True and parsed["asserting"] == [{"sentence": 2, "asserts": "b"}]
    assert parsed["position_a"]["sources"][0].url == EF.POSITIONS
    none = json.dumps({"site_id": EF.SITE_W, "disputed": False, "position_a": None,
                       "position_b": None, "asserting": [], "note": "settled"})  # fmt: skip
    assert D.parse_research(none, site_id=EF.SITE_W, sentences=3) == {
        "disputed": False,
        "note": "settled",
    }
    with pytest.raises(A.AnswerError, match="no position and asserts nothing"):
        D.parse_research(none.replace('"asserting": []', '"asserting": [{"sentence": 1, "asserts": "a"}]'),
                         site_id=EF.SITE_W, sentences=3)  # fmt: skip
    with pytest.raises(A.AnswerError, match="names site"):
        D.parse_research(none, site_id=EF.SITE_L, sentences=3)


def test_an_adjudication_confirms_or_denies_and_a_denial_asserts_nothing() -> None:
    ok = json.dumps({"site_id": "s", "verdict": "dispute", "asserting": [{"sentence": 1, "asserts": "a"}],
                     "note": "documented"})  # fmt: skip
    assert D.parse_adjudication(ok, site_id="s", sentences=2)["verdict"] == "dispute"
    denied = json.dumps(
        {"site_id": "s", "verdict": "not-a-dispute", "asserting": [], "note": "one view"}
    )
    assert D.parse_adjudication(denied, site_id="s", sentences=2)["asserting"] == []
    for bad, message in (
        (ok.replace('"dispute"', '"maybe"'), "verdict"),
        (ok.replace('"dispute"', '"not-a-dispute"'), "asserts nothing"),
        (ok.replace('"sentence": 1', '"sentence": 5'), "asserting names"),
    ):
        with pytest.raises(A.AnswerError, match=message):
            D.parse_adjudication(bad, site_id="s", sentences=2)


# ------------------------------------------------------------------------------ the rounds
@pytest.fixture
def screened(tmp_path: Path) -> dict[str, Any]:
    """A run with two candidates (a Phase-4 text with a dispute signal, and a second site) read and
    screened."""
    rows = [
        {**EF.p4_row(EF.SITE_W), "site_type": "Magnetic anomaly"},
        {**EF.p4_row(EF.SITE_NONE, name="Other"), "site_type": "Magnetic anomaly"},
    ]
    run = _run(tmp_path, rows)
    D.cmd_candidates(run, wiki_cache=None)
    return {"run": run, "rows": rows, "tmp": tmp_path}


def _record(handoff: Path, answers: dict[str, str], *, role: str, model: str, agent: str) -> None:
    for line in OH.manifest(handoff):
        if line["label"] in answers:
            OH.write_answer(
                handoff, model=model, batch_id=line["batch_id"], stage=line["stage"],
                label=line["label"], text=answers[line["label"]],
                answered_by=RO.answered_by(role, f"{agent}-{line['batch_id']}"),
                now=lambda: "2026-10-09T12:00:00+00:00",
            )  # fmt: skip


def _research_round(screened: dict[str, Any], answers: dict[str, str] | None = None) -> Path:
    handoff = screened["tmp"] / "handoff" / "ds"
    D.cmd_export(screened["run"], handoff)
    _record(
        handoff,
        answers or {EF.SITE_W: _research_answer(EF.SITE_W), EF.SITE_NONE: json.dumps(
            {"site_id": EF.SITE_NONE, "disputed": False, "position_a": None, "position_b": None,
             "asserting": [], "note": "one view only"})},
        role="field_researcher", model=OH.SONNET_MODEL, agent="sonnet-dispute",
    )  # fmt: skip
    return handoff


@pytest.mark.usefixtures("registry_until_d153")
def test_the_research_round_asks_one_question_per_candidate(screened: dict[str, Any]) -> None:
    run = screened["run"]
    summary = D.cmd_export(run, screened["tmp"] / "h")
    assert summary == {"questions": 2, "batches": 1}
    manifest = OH.manifest(screened["tmp"] / "h")
    assert {m["stage"] for m in manifest} == {"dispute"} and manifest[0]["batch_id"] == "ds-0001"
    prompt = (screened["tmp"] / "h" / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
    assert "whether it is DISPUTED" in prompt and "S1: The Tarxien Temples" in prompt
    assert "Magnetic anomaly" in prompt and "{site" not in prompt and "{sentences}" not in prompt
    with pytest.raises(D.DisputeError, match="was exported"):
        D.cmd_export(run, screened["tmp"] / "h2")
    text = D.brief(run, screened["tmp"] / "h", "ds-0001")
    assert "--role field_researcher --model claude-sonnet-5-5" in text and "--stage dispute" in text
    # the brief calls the agent by the registry's model, as the recording command does
    assert (
        "You are Sonnet researcher ds-0001" in text
        and "--answered-by sonnet-dispute-ds-0001" in text
    )
    assert "Opus" not in text


def test_check_answer_reports_the_shape_and_the_quotes_of_each_position(
    screened: dict[str, Any],
) -> None:
    run, tmp = screened["run"], screened["tmp"]
    D.cmd_export(run, tmp / "h")
    client = EF.pages_client()
    clean, report = D.check_answer(run, tmp / "h", "ds-0001", EF.SITE_W, _research_answer(EF.SITE_W),
                                   client=client, pace=0)  # fmt: skip
    assert (
        clean and "position_a: 1 of 1 quote(s) found" in report and "position_b: 1 of 1" in report
    )
    lost = _research_answer(
        EF.SITE_W,
        position_a=_position(
            quote={
                "title": "Dating Tarxien",
                "quote": "Nothing like this is written on the page at all.",
            }
        ),
    )
    clean, report = D.check_answer(
        run, tmp / "h", "ds-0001", EF.SITE_W, lost, client=client, pace=0
    )
    assert not clean and "NOT FOUND" in report and "NOT CLEAN" in report
    clean, report = D.check_answer(
        run, tmp / "h", "ds-0001", EF.SITE_W, "{}", client=client, pace=0
    )
    assert not clean and report.startswith("NOT IN SHAPE")


def test_the_import_checks_every_quote_and_ends_an_unverified_position(
    screened: dict[str, Any],
) -> None:
    lost = {"title": "Dating Tarxien", "quote": "Nothing like this is written on the page at all."}
    answers = {
        EF.SITE_W: _research_answer(
            EF.SITE_W, position_b={**_position(quote=lost), "claim": "x", "holders": "y"}
        ),
        EF.SITE_NONE: _research_answer(EF.SITE_NONE),
    }
    handoff = _research_round(screened, answers)
    summary = D.cmd_import(screened["run"], handoff, client=EF.pages_client(), pace=0.0)
    assert summary == {"researched": 1, "unverified": 1}
    rows = {r["site_id"]: r for r in read_jsonl(screened["run"] / D.RESEARCH_FILE)}
    assert rows[EF.SITE_W]["status"] == "unverified" and rows[EF.SITE_W]["position_b"]["failed"]
    assert rows[EF.SITE_NONE]["status"] == "researched"
    assert rows[EF.SITE_NONE]["position_a"]["sources"][0]["url"] == EF.POSITIONS
    with pytest.raises(D.DisputeError, match="was imported"):
        D.cmd_import(screened["run"], handoff, client=EF.pages_client(), pace=0.0)


@pytest.mark.usefixtures("registry_until_d153")
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"role": "web_verifier"}, "does not name the role 'field_researcher'"),
        ({"model": OH.OPUS_MODEL}, "registered to claude-sonnet-5-5"),
    ],
)
def test_the_research_import_refuses_an_answer_that_is_not_the_researchers_role(
    screened: dict[str, Any], kwargs: dict, message: str
) -> None:
    handoff = screened["tmp"] / "h"
    D.cmd_export(screened["run"], handoff)
    _record(handoff, {EF.SITE_W: _research_answer(EF.SITE_W), EF.SITE_NONE: _research_answer(EF.SITE_NONE)},
            **{"role": "field_researcher", "model": OH.SONNET_MODEL, "agent": "x", **kwargs})  # fmt: skip
    with pytest.raises(E.EnrichError, match=message):
        D.cmd_import(screened["run"], handoff, client=EF.pages_client(), pace=0.0)
    assert not (screened["run"] / D.RESEARCH_FILE).exists()


def _adjudicate(screened: dict[str, Any], verdicts: dict[str, dict], *, agent: str = "opus-adjudicate",
                role: str = "adversarial", model: str = OH.SONNET_MODEL) -> Path:  # fmt: skip
    handoff = _research_round(screened)
    D.cmd_import(screened["run"], handoff, client=EF.pages_client(), pace=0.0)
    h2 = screened["tmp"] / "handoff" / "da"
    D.cmd_adjudicate_export(screened["run"], h2)
    answers = {
        site: json.dumps({"site_id": site, "note": "weighed it", **body})
        for site, body in verdicts.items()
    }
    _record(h2, answers, role=role, model=model, agent=agent)
    return h2


@pytest.mark.usefixtures("registry_until_d153")
def test_the_adjudication_asks_the_researched_sites_and_an_independent_agent_answers(
    screened: dict[str, Any],
) -> None:
    ok = {"verdict": "dispute", "asserting": [{"sentence": 2, "asserts": "b"}]}
    h2 = _adjudicate(screened, {EF.SITE_W: ok})
    assert [m["label"] for m in OH.manifest(h2)] == [
        EF.SITE_W
    ]  # the not-disputed site was not asked
    prompt = (h2 / OH.manifest(h2)[0]["prompt_path"]).read_text(encoding="utf-8")
    assert (
        "you are the adversary" in prompt
        and "POSITION A: The first phase is near 3600 BC" in prompt
    )
    assert "source: " + EF.POSITIONS in prompt
    assert "--role adversarial --model claude-sonnet-5-5" in D.brief(
        screened["run"], h2, "da-0001", stage=D.ADJUDICATE_STAGE
    )
    assert D.cmd_adjudicate_import(screened["run"], h2) == {"dispute": 1}


@pytest.mark.usefixtures("registry_until_d153")
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"role": "field_researcher", "model": OH.SONNET_MODEL},
            "does not name the role 'adversarial'",
        ),
        ({"model": OH.OPUS_MODEL}, "registered to claude-sonnet-5-5"),
    ],
)
def test_the_adjudicator_is_the_adversarial_role_on_sonnet(
    screened: dict[str, Any], kwargs: dict, message: str
) -> None:
    h2 = _adjudicate(screened, {EF.SITE_W: {"verdict": "dispute", "asserting": []}}, **kwargs)
    with pytest.raises(E.EnrichError, match=message):
        D.cmd_adjudicate_import(screened["run"], h2)


def test_an_agent_that_researched_the_site_does_not_confirm_the_dispute(
    screened: dict[str, Any],
) -> None:
    h2 = _adjudicate(screened, {EF.SITE_W: {"verdict": "dispute", "asserting": []}})
    researched = read_jsonl(screened["run"] / D.RESEARCH_FILE)[0]["answered_by"]
    assert researched.startswith("field_researcher:")
    # the same agent under the adjudicator's role: the role is no other agent
    for line in OH.manifest(h2):
        path = h2 / OH.answer_relpath(line["batch_id"], line["stage"], line["label"])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["answered_by"] = "adversarial:" + WC4.agent_name(researched)
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(D.DisputeError, match="researched this site"):
        D.cmd_adjudicate_import(screened["run"], h2)


def test_only_a_confirmed_dispute_reaches_the_outputs(screened: dict[str, Any]) -> None:
    h2 = _adjudicate(
        screened,
        {EF.SITE_W: {"verdict": "dispute", "asserting": [{"sentence": 2, "asserts": "b"}]}},
    )
    D.cmd_adjudicate_import(screened["run"], h2)
    summary = D.cmd_outputs(screened["run"])
    assert (
        summary["disputes"] == 1
        and summary["sentences_to_repair"] == 1
        and summary["sites_to_repair"] == 1
    )
    assert summary["research"] == {"not-disputed": 1, "researched": 1}
    (record,) = read_jsonl(screened["run"] / D.DISPUTES_FILE)
    assert E.dispute_record_problems(record) == []
    assert set(record) == E.DISPUTE_KEYS and record["verdict"] == "dispute"
    assert record["asserting"] == [
        {"sentence": 2, "asserts": "b", "text": "They date to approximately 3150 BC."}
    ]
    assert record["position_a"]["sources"][0]["quote"] == EF.Q_A["quote"]
    assert record["researched_by"].startswith("field_researcher:")
    assert record["adjudicated_by"].startswith("adversarial:")
    assert record["desc_sha256"] == M.text_sha256(WX.P4_TEXT)


def test_a_denied_dispute_writes_no_brief_and_no_defect(screened: dict[str, Any]) -> None:
    h2 = _adjudicate(screened, {EF.SITE_W: {"verdict": "not-a-dispute", "asserting": []}})
    D.cmd_adjudicate_import(screened["run"], h2)
    summary = D.cmd_outputs(screened["run"])
    assert summary["disputes"] == 0 and summary["sentences_to_repair"] == 0
    assert read_jsonl(screened["run"] / D.DISPUTES_FILE) == []


def test_the_defect_lines_are_the_shape_the_site_list_reads_and_name_the_other_position(
    screened: dict[str, Any],
) -> None:
    h2 = _adjudicate(
        screened,
        {EF.SITE_W: {"verdict": "dispute", "asserting": [{"sentence": 2, "asserts": "b"}]}},
    )
    D.cmd_adjudicate_import(screened["run"], h2)
    D.cmd_outputs(screened["run"])
    (line,) = read_jsonl(screened["run"] / D.DEFECTS_FILE)
    assert set(line) == cli.DEFECT_KEYS
    assert line["sentence"] == 2 and line["sentence_text"] == "They date to approximately 3150 BC."
    assert (
        line["quote"] == EF.Q_A["quote"] and line["url"] == EF.POSITIONS
    )  # the OTHER position's page
    assert line["claim"].startswith(
        "DISPUTED: the sentence states as settled fact that The first phase is near 3150 BC"
    )
    assert "the excavators hold that The first phase is near 3600 BC" in line["claim"]
    assert (line["stage"], line["owner_lane"], line["basis"], line["proven"]) == (
        "dispute",
        "WE",
        "W",
        True,
    )
    assert line["quote_outcome"] == "found" and line["desc_sha256"] == M.text_sha256(WX.P4_TEXT)


def test_a_wc_list_run_reads_a_dispute_as_a_reported_claim(
    screened: dict[str, Any], tmp_path: Path
) -> None:
    """The feed end to end: `defect-sites` over `DISPUTE_DEFECTS.jsonl` lists the site and reports the
    claim; `export --sites --defects` puts it into the check question (the `DEFECTS_HEAD`)."""
    h2 = _adjudicate(
        screened,
        {EF.SITE_W: {"verdict": "dispute", "asserting": [{"sentence": 2, "asserts": "b"}]}},
    )
    D.cmd_adjudicate_import(screened["run"], h2)
    D.cmd_outputs(screened["run"])
    run = screened["run"]
    sites = run / "SITES.txt"
    report = cli.cmd_defect_sites(run, [run / D.DEFECTS_FILE], sites)
    assert report["sites"] == 1 and report["by_owner_lane"] == {"WE": 1}
    assert sites.read_text(encoding="utf-8").split() == [EF.SITE_W]
    handoff = tmp_path / "list-h"
    cli.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None,
                   sites=sites, defects=sites.with_name(sites.name + ".report.json"))  # fmt: skip
    (manifest,) = OH.manifest(handoff)
    prompt = (handoff / manifest["prompt_path"]).read_text(encoding="utf-8")
    assert "A LATER WEB CHECK REPORTED A CLAIM OF THIS DESCRIPTION CONTRADICTED" in prompt
    assert 'S2: claim "DISPUTED: the sentence states as settled fact' in prompt
    assert EF.POSITIONS in prompt


# ------------------------------------------------------------------------------ the briefs of one run
STATED = "They date to approximately 3150 BC."
NO_ROW = "ffffffff-0000-4000-8000-000000000001"


@pytest.fixture
def confirmed(tmp_path: Path) -> dict[str, Any]:
    """A dispute run with seven confirmed briefs, the read of an enrichment run that can take two
    of them, and an earlier enrichment run (the pilot) that asked one of the others."""
    rows = [
        EF.p4_row(EF.SITE_W),
        EF.p4_row(EF.SITE_L, name="Second"),
        EF.p4_row(EF.SITE_N, name="In the pilot"),
        EF.p4_row(EF.SITE_NONE, name="Asserting"),
        FX.row(EF.SITE_BAD, WX.P4_TEXT, raw_data=WX.p4_site_raw(), scope_status="retired"),
        FX.row(FX.SITE_A, "A text no lane has marked or checked.", name="Unmarked"),
    ]
    briefs = [
        EF.dispute_brief(EF.SITE_NONE, asserting=[{"sentence": 2, "asserts": "b", "text": STATED}]),
        EF.dispute_brief(EF.SITE_W),
        EF.dispute_brief(EF.SITE_BAD),
        EF.dispute_brief(NO_ROW),
        EF.dispute_brief(EF.SITE_N),
        # made for an earlier text; the sentence it names is not in the text the read holds
        EF.dispute_brief(
            EF.SITE_L,
            asserting=[{"sentence": 2, "asserts": "a", "text": "It is a pyramid."}],
            desc_sha256="e" * 64,
        ),
        EF.dispute_brief(FX.SITE_A),
    ]
    disputes = tmp_path / "dispute_runs" / "d"
    disputes.mkdir(parents=True)
    (disputes / D.DISPUTES_FILE).write_text(
        "".join(json.dumps(b) + "\n" for b in briefs), encoding="utf-8"
    )
    pilot, _ = EF.start_enrich_run(tmp_path / "p", rows, sites=[EF.SITE_N], name="pilot")
    run = tmp_path / "runs" / "rest"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    return {"disputes": disputes, "briefs": briefs, "pilot": pilot, "run": run, "rows": rows}


def test_the_briefs_a_run_can_take_are_written_and_the_others_are_held_with_their_reason(
    confirmed: dict[str, Any], tmp_path: Path
) -> None:
    """`DISPUTES.jsonl` holds every confirmed dispute; an enrichment run asks only some of their
    sites. `briefs --for-run` decides on that run's read as its export will, and writes the subset
    the export takes, its site list and the held briefs - the full file is never cut by hand."""
    out = tmp_path / "drv" / "enrich-rest.briefs.jsonl"
    summary = D.cmd_briefs(
        confirmed["disputes"], for_run=confirmed["run"], out=out, after=[confirmed["pilot"]]
    )
    assert (summary["briefs"], summary["usable"], summary["pilot_size"]) == (7, 2, 2)
    assert summary["held"] == {
        "asserting-in-text": 1,
        "earlier-run": 1,
        "no-curated-row": 1,
        "no-provenance": 1,
        "retired": 1,
    }
    briefs = confirmed["briefs"]
    assert read_jsonl(out) == [briefs[1], briefs[5]]  # unchanged, in the file's order
    sites = out.with_name(out.name + D.BRIEF_SITES_SUFFIX)
    assert sites.read_bytes() == f"{EF.SITE_W}\n{EF.SITE_L}\n".encode()
    assert summary["out"] == {"path": cli._shown(out), "sha256": cli._sha256(out)}
    held = json.loads(out.with_name(out.name + D.BRIEFS_HELD_SUFFIX).read_text(encoding="utf-8"))
    assert {h["site_id"]: (h["reason"], h["asserting_in_text"]) for h in held} == {
        EF.SITE_NONE: ("asserting-in-text", [2]),
        EF.SITE_BAD: ("retired", []),
        NO_ROW: ("no-curated-row", []),
        EF.SITE_N: ("earlier-run", []),
        FX.SITE_A: ("no-provenance", []),
    }
    assert all(h["name"] == "Tarxien Temples" for h in held)

    def export(handoff: str, disputes: Path) -> dict[str, Any]:
        return cli.cmd_export(
            confirmed["run"], tmp_path / handoff, batch_size=5, exclude=None,
            after=[confirmed["pilot"]], pilot=2, seed=1, sites=sites, enrich=True,
            disputes=disputes,
        )  # fmt: skip

    # the whole file is refused, and the refusal names the command; the subset is what is taken
    with pytest.raises(cli.WcRunError, match="is no site this run asks - disputes.py briefs"):
        export("h-all", confirmed["disputes"] / D.DISPUTES_FILE)
    assert export("h", out)["questions"] == 2
    population = json.loads((confirmed["run"] / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["disputes"] == {
        "path": cli._shown(out), "sha256": cli._sha256(out), "sites": 2,
    }  # fmt: skip
    entries = read_jsonl(confirmed["run"] / cli.SITES_FILE)
    assert [e["dispute"]["site_id"] for e in entries] == [EF.SITE_W, EF.SITE_L]


def test_the_briefs_of_a_run_without_an_earlier_one_take_the_pilot_s_site_too(
    confirmed: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "pilot.briefs.jsonl"
    summary = D.cmd_briefs(confirmed["disputes"], for_run=confirmed["run"], out=out)
    assert summary["usable"] == 3 and "earlier-run" not in summary["held"]
    assert [b["site_id"] for b in read_jsonl(out)] == [EF.SITE_W, EF.SITE_N, EF.SITE_L]


def test_the_briefs_leave_out_the_sites_the_export_is_told_to_exclude(
    confirmed: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run exported with `--exclude` is given the briefs decided with the same file: the brief of
    a site the run leaves out is held `excluded`. The subset decided without the file is refused
    whole by that export, as the full `DISPUTES.jsonl` is."""
    disputes, run, pilot = confirmed["disputes"], confirmed["run"], confirmed["pilot"]
    exclude = tmp_path / "exclude.txt"
    exclude.write_text(f"{EF.SITE_L}\n", encoding="utf-8")
    without = tmp_path / "without.briefs.jsonl"
    assert D.cmd_briefs(disputes, for_run=run, out=without, after=[pilot])["exclude"] is None
    out = tmp_path / "b.jsonl"
    summary = D.cmd_briefs(disputes, for_run=run, out=out, after=[pilot], exclude=exclude)
    assert summary["usable"] == 1 and summary["held"]["excluded"] == 1
    assert summary["exclude"] == {"path": cli._shown(exclude), "sha256": cli._sha256(exclude)}
    assert [b["site_id"] for b in read_jsonl(out)] == [EF.SITE_W]
    held = json.loads(out.with_name(out.name + D.BRIEFS_HELD_SUFFIX).read_text(encoding="utf-8"))
    assert {h["site_id"]: h["reason"] for h in held}[EF.SITE_L] == "excluded"

    def export(handoff: str, briefs: Path) -> dict[str, Any]:
        return cli.cmd_export(
            run, tmp_path / handoff, batch_size=5, exclude=exclude, after=[pilot], pilot=1, seed=1,
            sites=briefs.with_name(briefs.name + D.BRIEF_SITES_SUFFIX), enrich=True,
            disputes=briefs,
        )  # fmt: skip

    with pytest.raises(cli.WcRunError, match=f"{EF.SITE_L} is no site this run asks"):
        export("h-without", without)
    assert export("h", out)["questions"] == 1
    # the command line takes the file as the export does, and refuses one that names no site id
    argv = ["briefs", "--run-dir", str(disputes), "--for-run", str(run), "--after", str(pilot),
            "--exclude", str(exclude), "--out", str(tmp_path / "c.jsonl")]  # fmt: skip
    assert D.main(argv) == 0
    assert '"excluded": 1' in capsys.readouterr().out
    assert read_jsonl(tmp_path / "c.jsonl") == read_jsonl(out)
    exclude.write_text("Tarxien Temples\n", encoding="utf-8")
    assert D.main(argv) == 1
    assert "REFUSED" in capsys.readouterr().err


def test_the_briefs_command_refuses_what_it_cannot_decide(
    confirmed: dict[str, Any], tmp_path: Path
) -> None:
    disputes, run, out = confirmed["disputes"], confirmed["run"], tmp_path / "b.jsonl"
    with pytest.raises(D.DisputeError, match="the outputs were not written"):
        D.cmd_briefs(tmp_path / "none", for_run=run, out=out)
    with pytest.raises(D.DisputeError, match="no read"):
        D.cmd_briefs(disputes, for_run=tmp_path / "unread", out=out)
    path = disputes / D.DISPUTES_FILE
    whole = path.read_text(encoding="utf-8")
    path.write_text(whole + json.dumps(confirmed["briefs"][1]) + "\n", encoding="utf-8")
    with pytest.raises(D.DisputeError, match=f"8: {EF.SITE_W} has two dispute briefs"):
        D.cmd_briefs(disputes, for_run=run, out=out)
    path.write_text(
        whole + json.dumps({**EF.dispute_brief(FX.SITE_B), "verdict": "settled"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(D.DisputeError, match="8: verdict 'settled'"):
        D.cmd_briefs(disputes, for_run=run, out=out)
    assert not out.exists()


# ------------------------------------------------------------------------------ the command line
def test_the_command_line_screens_and_refuses_with_a_line_of_its_own(
    screened: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    run = screened["run"]
    assert D.main(["candidates", "--run-dir", str(run)]) == 0
    assert "DISPUTE_EXIT=0" in capsys.readouterr().out
    assert (
        D.main(
            ["adjudicate-export", "--run-dir", str(run), "--handoff", str(screened["tmp"] / "x")]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err and "DISPUTE_EXIT=1" in captured.out
    assert (
        D.main(["recall", "--run-dir", str(run)]) == 1
    )  # two candidates: far below the known positives


def test_the_command_line_takes_the_include_list_and_writes_the_briefs_of_a_run(
    confirmed: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _run(tmp_path / "screen", [_row(FX.SITE_B, PLAIN)])
    include = _include(tmp_path, FX.SITE_B)
    assert D.main(["candidates", "--run-dir", str(run), "--include", str(include)]) == 0
    assert '"candidates": 1' in capsys.readouterr().out
    out = tmp_path / "b.jsonl"
    argv = ["briefs", "--run-dir", str(confirmed["disputes"]), "--for-run", str(confirmed["run"]),
            "--after", str(confirmed["pilot"]), "--out", str(out)]  # fmt: skip
    assert D.main(argv) == 0
    printed = capsys.readouterr().out
    assert '"usable": 2' in printed and "DISPUTE_EXIT=0" in printed
    assert len(read_jsonl(out)) == 2
    assert D.main([*argv[:4], str(tmp_path / "unread"), *argv[5:]]) == 1
    assert "REFUSED" in capsys.readouterr().err

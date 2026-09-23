"""The attribution backfill (`scripts/remediation/gallery_audit/attribution.py`): four routes to a
CC BY* image's author, each from an exact span of the Commons file page, and nothing guessed.

Offline. Pages are built in the test; the fetch path runs the real `census.fetch.Fetcher` (its
User-Agent, its cache) over an `httpx.MockTransport` that answers like the Commons API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import attribution as A  # noqa: E402
from census.fetch import USER_AGENT, Fetcher  # noqa: E402

SITE = "00000000-0000-4000-8000-000000000001"
USER_ANCHOR = '<a href="//commons.wikimedia.org/wiki/User:Udimu" title="User:Udimu">Udimu</a>'
OWN_WORK = '<span class="int-own-work" lang="en">Own work</span>'


def _page(ext: dict[str, str] | None = None, wikitext: str = "", revid: int = 100) -> A.Page:
    return A.Page(
        title="File:Temple.jpg",
        revid=revid,
        timestamp="2026-01-01T00:00:00Z",
        wikitext=wikitext,
        extmetadata=ext or {},
        retrieved_at="2026-09-23T06:00:00+0000",
        response_sha256="ab" * 32,
    )


def _info(author: str) -> str:
    return "== {{int:filedesc}} ==\n{{Information\n|description=x\n|author = " + author + "\n}}\n"


def _row(image_id: int = 7, **over) -> A.Row:
    base = {
        "id": image_id,
        "site_id": SITE,
        "author": None,
        "author_url": None,
        "license": "CC BY-SA 3.0",
        "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Temple.jpg",
        "commons_page_url": "https://commons.wikimedia.org/wiki/File%3ATemple.jpg",
    }
    base.update(over)
    return A.Row(**base)


# --------------------------------------------------------------------------------------------
# the routes, in order
# --------------------------------------------------------------------------------------------


def test_a1_reads_the_artist_field_as_parse_attribution_does():
    found = A.resolve(_page({"Artist": USER_ANCHOR, "Attribution": "Someone else"}))
    assert isinstance(found, A.Found)
    assert (found.rule, found.field, found.span) == ("A1", "Artist", USER_ANCHOR)
    assert (found.author, found.author_url) == ("Udimu", "https://commons.wikimedia.org/wiki/User:Udimu")


def test_an_empty_artist_field_moves_on_to_the_attribution_line():
    found = A.resolve(_page({"Artist": "<span></span> ", "Attribution": "Steve Woolf"}))
    assert isinstance(found, A.Found)
    assert (found.rule, found.author, found.author_url) == ("A2", "Steve Woolf", None)


def test_a_present_field_that_cannot_be_read_exactly_ends_the_row():
    """No fall-through past a field that is there: its reason is the row's."""
    found = A.resolve(
        _page({"Attribution": "\N{REPLACEMENT CHARACTER} Codrin.B", "Credit": f"{USER_ANCHOR} ({OWN_WORK})"})
    )
    assert isinstance(found, A.Refused)
    assert found.rule == "A2" and "replacement character" in found.reason


def test_a3_takes_the_one_user_link_of_an_own_work_credit():
    found = A.resolve(_page({"Credit": f"{USER_ANCHOR} ({OWN_WORK})"}))
    assert isinstance(found, A.Found)
    assert (found.rule, found.span, found.author) == ("A3", USER_ANCHOR, "Udimu")


@pytest.mark.parametrize(
    "credit",
    [
        OWN_WORK,  # the {{Own}} tag with no user link
        f"{USER_ANCHOR} and {USER_ANCHOR.replace('Udimu', 'Other')} ({OWN_WORK})",  # two users
        f"{USER_ANCHOR} (Own work (photo))",  # no own-work marker
    ],
)
def test_a_credit_without_exactly_one_user_link_and_the_marker_is_not_a3(credit):
    found = A.resolve(_page({"Credit": credit}))
    assert isinstance(found, A.Refused) and found.rule == "-"


@pytest.mark.parametrize(
    ("author", "want"),
    [
        ("[[User:Letterix|ingostrutz]]", ("ingostrutz", "https://commons.wikimedia.org/wiki/User:Letterix")),
        ("[[User:Simon Burchell]]", ("Simon Burchell", "https://commons.wikimedia.org/wiki/User:Simon_Burchell")),
        ("[[:en:User:Bobak|Bobak Ha'Eri]]", ("Bobak Ha'Eri", "https://en.wikipedia.org/wiki/User:Bobak")),
        ("[https://www.flickr.com/photos/x Claire H.]", ("Claire H.", "https://www.flickr.com/photos/x")),
        ("Helena Rosengren", ("Helena Rosengren", None)),
    ],
)
def test_a4_reads_one_link_or_plain_text_from_the_information_author(author, want):
    found = A.resolve(_page(wikitext=_info(author)))
    assert isinstance(found, A.Found)
    assert (found.rule, found.span) == ("A4", author)
    assert (found.author, found.author_url) == want
    # the stored markup re-derives the author through the one shared normalizer
    again = A.parse_attribution({"extmetadata": {"Artist": {"value": found.html}}})
    assert (again["author"], again["author_url"]) == want


@pytest.mark.parametrize(
    ("author", "says"),
    [
        ("{{U|Codrinb|Codrin.B}}", "markup this lane does not read exactly"),
        ("Drawn by [[:en:User:Adamsan|Adamsan]]", "markup this lane does not read exactly"),
        ("{{Creator:Edward Rooker}}", "markup this lane does not read exactly"),
        ("Unknown", "names no one"),
        ("x" * 201, "longer than 200 characters"),
    ],
)
def test_a4_refuses_what_it_cannot_read_exactly(author, says):
    found = A.resolve(_page(wikitext=_info(author)))
    assert isinstance(found, A.Refused)
    assert found.rule == "A4" and says in found.reason


def test_an_empty_or_doubled_information_template_gives_no_route():
    assert isinstance(A.resolve(_page(wikitext=_info(""))), A.Refused)
    # the Dispilio page: an unclosed template swallowed a second one
    nested = "{{Information\n|Date=== {{int:filedesc}} ==\n" + _info("[[User:X|X]]") + "}}"
    # and two complete templates that name two authors: which one is the file's is not ours to pick
    two = _info("[[User:A|A]]") + _info("[[User:B|B]]")
    for wikitext in (nested, two):
        found = A.resolve(_page(wikitext=wikitext))
        assert isinstance(found, A.Refused) and found.rule == "-", wikitext


def test_an_entity_parse_attribution_would_store_literally_is_refused():
    redlink = (
        '<a href="//commons.wikimedia.org/w/index.php?title=User:Hotgor&amp;action=edit&amp;'
        'redlink=1" class="new">Hotgor</a>'
    )
    found = A.resolve(_page({"Artist": redlink}))
    assert isinstance(found, A.Refused) and "HTML entity" in found.reason


# --------------------------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------------------------


def test_the_plan_writes_author_and_its_url_with_a_pointer_to_the_evidence_line():
    plan = A.build_plan([_row()], {"Temple.jpg": _page({"Artist": USER_ANCHOR})})
    assert [(c.column, c.old_value, c.new_value) for c in plan.changes] == [
        ("author", None, "Udimu"),
        ("author_url", None, "https://commons.wikimedia.org/wiki/User:Udimu"),
    ]
    (record,) = plan.evidence
    assert record["span"] == USER_ANCHOR and record["span_sha256"] == A.sha256(USER_ANCHOR)
    pointer = plan.changes[0].evidence[0]
    assert pointer["evidence_sha256"] == A.canonical_sha256(record)
    assert pointer["revid"] == 100 and "oldid=100" in pointer["url"]
    assert "span" not in pointer  # the journal carries pointers, not the text


def test_a_span_without_a_link_writes_the_author_only():
    plan = A.build_plan([_row()], {"Temple.jpg": _page({"Attribution": "Steve Woolf"})})
    assert [c.column for c in plan.changes] == ["author"]


def test_a_row_whose_url_is_another_sources_is_listed_not_mixed():
    plan = A.build_plan(
        [_row(author_url="https://www.flickr.com/people/x")],
        {"Temple.jpg": _page({"Artist": USER_ANCHOR})},
    )
    assert plan.changes == []
    assert "one credit may not mix two sources" in plan.unresolved[0]["reason"]


def test_every_unresolved_row_is_listed_with_its_reason():
    rows = [_row(1), _row(2, original_url=None, commons_page_url=None), _row(3)]
    pages = {"Temple.jpg": "missing"}
    plan = A.build_plan(rows, pages)
    assert plan.changes == []
    assert [(u["image_id"], u["reason"]) for u in plan.unresolved] == [
        (1, "commons: missing"),
        (2, "the row has no Commons identity"),
        (3, "commons: missing"),
    ]


def test_a_row_that_already_has_an_author_stops_the_lane():
    with pytest.raises(A.AttributionError, match="already has an author"):
        A.build_plan([_row(author="Someone")], {})


def test_the_lane_writes_only_author_columns_in_chunks_of_the_shared_writer(tmp_path):
    pages = {"Temple.jpg": _page({"Artist": USER_ANCHOR})}
    plan = A.build_plan([_row(1), _row(2)], pages)
    assert {c.column for c in plan.changes} == {"author", "author_url"}
    (chunk,) = A.CW.chunk_changes(A.LANE, plan.changes)
    assert chunk.run_stamp == "img-attrib-2026-09-23-001"
    directory = A.CW.emit_chunk(tmp_path, chunk)
    assert A.CW.check_delivered(directory).lane == A.LANE


# --------------------------------------------------------------------------------------------
# the fetch: the real Fetcher over a Commons-shaped transport
# --------------------------------------------------------------------------------------------


def _commons_answer(request: httpx.Request) -> httpx.Response:
    titles = request.url.params["titles"].split("|")
    pages = []
    for title in titles:
        if title == "File:Gone.jpg":
            pages.append({"ns": 6, "title": title, "missing": True})
            continue
        pages.append(
            {
                "ns": 6,
                "title": title.replace("_", " "),
                "imageinfo": [{"extmetadata": {"Artist": {"value": USER_ANCHOR}}}],
                "revisions": [
                    {
                        "revid": 555,
                        "timestamp": "2026-01-01T00:00:00Z",
                        "slots": {"main": {"content": _info("[[User:Udimu|Udimu]]")}},
                    }
                ],
            }
        )
    normalized = [{"from": t, "to": t.replace("_", " ")} for t in titles if "_" in t]
    return httpx.Response(200, json={"query": {"normalized": normalized, "pages": pages}})


def test_the_fetch_maps_every_name_through_normalisation_and_names_missing_files(tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _commons_answer(request)

    with Fetcher(root=tmp_path, workers=1, transport=httpx.MockTransport(handler)) as fetcher:
        pages = A.fetch_batch(fetcher, ["Temple_gate.jpg", "Gone.jpg"])
    page = pages["Temple_gate.jpg"]
    assert isinstance(page, A.Page) and page.title == "File:Temple gate.jpg" and page.revid == 555
    assert pages["Gone.jpg"] == "missing"
    (request,) = seen
    assert request.headers["user-agent"] == USER_AGENT
    assert request.url.params["prop"] == "imageinfo|revisions"
    assert request.url.params["rvslots"] == "main" and request.url.params["maxlag"] == "5"


def test_a_maxlag_refusal_is_asked_again_and_then_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "PAUSE_S", 0.0)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"error": {"code": "maxlag", "info": "lagged"}})

    with Fetcher(root=tmp_path, workers=1, transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(A.AttributionError, match="refused a batch three times"):
            A.fetch_batch(fetcher, ["Temple.jpg"])
    assert len(calls) == 3


# --------------------------------------------------------------------------------------------
# the recheck
# --------------------------------------------------------------------------------------------


def test_the_recheck_passes_on_the_same_page_and_names_every_drift():
    page = _page({"Artist": USER_ANCHOR})
    plan = A.build_plan([_row()], {"Temple.jpg": page})
    evidence = plan.evidence
    assert A.recheck(evidence, {"Temple.jpg": page}) == []
    moved = _page({"Artist": USER_ANCHOR}, revid=101)
    assert "moved from revid 100 to 101" in A.recheck(evidence, {"Temple.jpg": moved})[0]
    edited = _page({"Artist": USER_ANCHOR.replace("Udimu</a>", "Udimu2</a>")})
    assert "no longer reads the same" in A.recheck(evidence, {"Temple.jpg": edited})[0]
    assert "now answers 'missing'" in A.recheck(evidence, {"Temple.jpg": "missing"})[0]
    tampered = [dict(evidence[0], author="Someone else")]
    assert "not the planned author" in A.recheck(tampered, {"Temple.jpg": page})[0]


def test_the_evidence_file_is_one_canonical_json_line_per_resolved_row(tmp_path):
    plan = A.build_plan([_row(1), _row(2)], {"Temple.jpg": _page({"Artist": USER_ANCHOR})})
    path = tmp_path / "EVIDENCE.jsonl"
    A.write_jsonl(path, plan.evidence)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["image_id"] for line in lines] == [1, 2]
    assert all(line == json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True) for line in lines)

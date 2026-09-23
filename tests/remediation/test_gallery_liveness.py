"""The Commons liveness sweep (`scripts/remediation/gallery_audit/liveness.py`).

The sweep runs through the real `census.fetch.Fetcher` against a fake Commons: an
`httpx.MockTransport` that parses the query string it is given and answers the way the API does
(measured 2026-09-23): titles are normalised (`_` -> space), `redirects=1` resolves a redirect,
a missing file carries `missing: true` and no page id, more than 50 titles are truncated with a
warning, a too-long URI is refused with HTTP 414, and `maxlag` is an HTTP 200 with an `error`
object. The fake refuses what Commons refuses, so a sweep that sent a malformed request fails here
too.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from census.fetch import Fetcher  # noqa: E402
from census.snapshot import SnapshotError  # noqa: E402
from gallery_audit import liveness as L  # noqa: E402

SNAPSHOT = REPO / "output" / "remediation" / "snapshot"
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "wiki_images.jsonl.gz").exists(),
    reason=f"{SNAPSHOT} is gitignored working data and not on this checkout",
)

UPLOAD = "https://upload.wikimedia.org/wikipedia/commons"


def _normalise(title: str) -> str:
    title = title.replace("_", " ")
    ns, _, rest = title.partition(":")
    return f"{ns}:{rest[:1].upper()}{rest[1:]}"


class FakeCommons:
    """Answers `action=query` as commons.wikimedia.org does, for the titles it knows."""

    TITLE_LIMIT = 50

    def __init__(
        self,
        files: dict[str, dict[str, Any]],
        *,
        redirects: dict[str, str] | None = None,
        logs: dict[str, list[dict[str, Any]]] | None = None,
        max_uri: int = 100_000,
    ) -> None:
        self.files = files
        self.redirects = redirects or {}
        self.logs = logs or {}
        self.max_uri = max_uri
        self.requests: list[dict[str, list[str]]] = []
        self.maxlag_answers = 0
        self.drop_titles: set[str] = set()
        self.truncate_logs = False
        #: answers given verbatim before any parsed one: (status, body text)
        self.raw_answers: list[tuple[int, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if len(str(request.url)) > self.max_uri:
            return httpx.Response(414, text="Request-URI Too Long")
        params = parse_qs(urlsplit(str(request.url)).query, keep_blank_values=True)
        self.requests.append(params)
        assert params["action"] == ["query"] and params["format"] == ["json"]
        assert params["formatversion"] == ["2"]
        if self.raw_answers:
            status, text = self.raw_answers.pop(0)
            return httpx.Response(status, text=text)
        if self.maxlag_answers:
            self.maxlag_answers -= 1
            return httpx.Response(
                200,
                json={
                    "error": {
                        "code": "maxlag",
                        "info": "Waiting for a database server: 6 seconds lagged.",
                    }
                },
            )
        if params.get("prop") == ["imageinfo"]:
            return httpx.Response(200, json=self._imageinfo(params))
        if params.get("list") == ["logevents"]:
            return httpx.Response(200, json=self._logevents(params))
        return httpx.Response(200, json={"error": {"code": "badvalue", "info": str(params)}})

    def _imageinfo(self, params: dict[str, list[str]]) -> dict[str, Any]:
        assert params["iiprop"] == [L.IIPROP]
        titles = params["titles"][0].split("|")
        body: dict[str, Any] = {"batchcomplete": True, "query": {}}
        if len(titles) > self.TITLE_LIMIT:
            body["warnings"] = {
                "main": {
                    "warnings": 'Too many values supplied for parameter "titles". The limit is 50.'
                }
            }
            titles = titles[: self.TITLE_LIMIT]
        normalized, redirects, pages = [], [], []
        for raw in titles:
            if raw in self.drop_titles:
                continue
            if "<" in raw:
                pages.append({"title": raw, "invalidreason": "illegal characters", "invalid": True})
                continue
            title = _normalise(raw)
            if title != raw:
                normalized.append({"fromencoded": False, "from": raw, "to": title})
            if title in self.redirects:
                redirects.append({"from": title, "to": self.redirects[title]})
                title = self.redirects[title]
            known = self.files.get(title)
            if known is None:
                pages.append({"ns": 6, "title": title, "missing": True, "imagerepository": ""})
            else:
                info = {k: known[k] for k in ("timestamp", "width", "height") if k in known}
                info["url"] = (
                    known["url"] + "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo"
                )
                page = {
                    "pageid": known["pageid"],
                    "ns": 6,
                    "title": title,
                    "imagerepository": "local",
                }
                if known.get("no_file"):
                    page["imagerepository"] = ""
                else:
                    page["imageinfo"] = [info]
                pages.append(page)
        if normalized:
            body["query"]["normalized"] = normalized
        if redirects:
            body["query"]["redirects"] = redirects
        body["query"]["pages"] = pages
        return body

    def _logevents(self, params: dict[str, list[str]]) -> dict[str, Any]:
        assert params["leprop"] == [L.LEPROP]
        title = _normalise(params["letitle"][0])
        body: dict[str, Any] = {
            "batchcomplete": True,
            "query": {"logevents": list(self.logs.get(title, []))},
        }
        if self.truncate_logs:
            body["continue"] = {"lecontinue": "20260101000000|1", "continue": "-||"}
        return body


def _upload(name: str) -> dict[str, Any]:
    return {
        "pageid": abs(hash(name)) % 10_000_000,
        "width": 2400,
        "height": 1600,
        "timestamp": "2020-01-01T00:00:00Z",
        "url": f"{UPLOAD}/a/ab/{name.replace(' ', '_')}",
    }


def _event(
    logid: int, type_: str, action: str, ts: str, comment: str = "", **params: Any
) -> dict[str, Any]:
    return {
        "logid": logid,
        "ns": 6,
        "pageid": 0,
        "logpage": 1,
        "params": params,
        "type": type_,
        "action": action,
        "timestamp": ts,
        "comment": comment,
    }


def _commons() -> FakeCommons:
    files = {
        f"File:{n}": _upload(n)
        for n in ("Alive one.jpg", "New name.jpg", "Forum Romanum - panoramio (3).jpg")
    }
    files["File:Page only.jpg"] = {**_upload("Page only.jpg"), "no_file": True}
    logs = {
        "File:Copyvio.jpg": [
            _event(
                9,
                "delete",
                "delete",
                "2026-09-14T08:22:32Z",
                "[[COM:L|Copyright violation]]: Copyrighted text material",
            ),
            _event(3, "upload", "upload", "2021-08-22T20:05:15Z", "Transferred from Flickr"),
        ],
        "File:Deletion request.jpg": [
            _event(
                8,
                "delete",
                "delete",
                "2026-09-01T10:28:27Z",
                "per [[Commons:Deletion requests/File:Deletion request.jpg]]",
            ),
        ],
        "File:- panoramio (1931).jpg": [
            _event(
                7,
                "move",
                "move",
                "2026-09-16T00:59:40Z",
                "[[Commons:FR#FR2|Criterion 2]]",
                target_ns=6,
                target_title="File:Forum Romanum - panoramio (3).jpg",
                suppressredirect=True,
            ),
            _event(2, "upload", "upload", "2016-11-22T11:18:41Z"),
        ],
        "File:Moved then deleted.jpg": [
            _event(5, "move", "move", "2025-01-01T00:00:00Z", target_title="File:Elsewhere.jpg"),
            _event(6, "delete", "delete", "2026-02-01T00:00:00Z", "Copyvio: see source"),
        ],
    }
    return FakeCommons(files, redirects={"File:Old name.jpg": "File:New name.jpg"}, logs=logs)


FILES = {
    "Alive_one.jpg": [11, 12],
    "Old_name.jpg": [13],
    "Copyvio.jpg": [14],
    "Deletion_request.jpg": [15],
    "-_panoramio_(1931).jpg": [16],
    "Moved_then_deleted.jpg": [17],
    "Never_logged.jpg": [18],
    "Page_only.jpg": [19],
    "Bad<name>.jpg": [20],
}


class Clock:
    """A clock and a sleep that share one time line, so pacing is measured, not slept."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _sweep(
    tmp_path: Path,
    commons: FakeCommons,
    files: dict[str, list[int]] = FILES,
    clock: Clock | None = None,
):
    clock = clock or Clock()
    pace = L.Pace(1.0, clock=clock, sleep=clock.sleep)
    with Fetcher(
        tmp_path / "cache", workers=1, max_retries=1, transport=httpx.MockTransport(commons)
    ) as fetcher:
        lines = L.sweep(files, fetcher, ns="liveness-test", pace=pace)
    return {line["file"]: line for line in lines}, pace, clock


def test_every_class_is_read_from_what_commons_answers(tmp_path: Path) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    classes = {name: line["class"] for name, line in lines.items()}
    assert classes == {
        "Alive_one.jpg": L.LIVE,
        "Old_name.jpg": L.MOVED_WITH_REDIRECT,
        "Copyvio.jpg": L.DELETED_COPYVIO,
        "Deletion_request.jpg": L.DELETED_OTHER,
        "-_panoramio_(1931).jpg": L.MOVED_WITHOUT_REDIRECT,
        "Moved_then_deleted.jpg": L.DELETED_COPYVIO,
        "Never_logged.jpg": L.MISSING_NO_LOG,
        "Page_only.jpg": L.PAGE_WITHOUT_FILE,
        "Bad<name>.jpg": L.INVALID_TITLE,
    }
    alive = lines["Alive_one.jpg"]
    assert alive["image_ids"] == [11, 12]
    assert alive["title"] == "File:Alive one.jpg" and alive["width"] == 2400
    assert alive["url"] == f"{UPLOAD}/a/ab/Alive_one.jpg"  # the utm query is stripped
    assert len(alive["raw_sha256"]) == 64 and alive["log"] is None
    assert lines["Old_name.jpg"]["title"] == "File:New name.jpg"
    copyvio = lines["Copyvio.jpg"]
    assert copyvio["log"]["logid"] == 9 and copyvio["pageid"] is None
    assert len(copyvio["log_raw_sha256"]) == 64
    moved = lines["-_panoramio_(1931).jpg"]
    assert moved["log"]["params"]["suppressredirect"] is True
    assert moved["move_target"]["title"] == "File:Forum Romanum - panoramio (3).jpg"
    assert moved["move_target"]["class"] == L.LIVE
    assert moved["move_target"]["url"] == f"{UPLOAD}/a/ab/Forum_Romanum_-_panoramio_(3).jpg"


def test_the_newest_deletion_or_move_decides_and_uploads_do_not() -> None:
    events = [
        _event(1, "move", "move", "2025-01-01T00:00:00Z", target_title="File:X.jpg"),
        _event(2, "upload", "overwrite", "2026-05-01T00:00:00Z"),
        _event(3, "delete", "delete", "2026-02-01T00:00:00Z", "reason"),
        _event(4, "delete", "restore", "2026-06-01T00:00:00Z"),
    ]
    assert L.latest_relevant(events)["logid"] == 3
    assert L.latest_relevant([_event(2, "upload", "upload", "2020-01-01T00:00:00Z")]) is None


@pytest.mark.parametrize(
    ("comment", "cls"),
    [
        ("[[COM:L|Copyright violation]]: Copyrighted text material", L.DELETED_COPYVIO),
        ("Copyvio: https://example.org", L.DELETED_COPYVIO),
        ("per [[Commons:Deletion requests/File:X.jpg]]", L.DELETED_OTHER),
        ("", L.DELETED_OTHER),
    ],
)
def test_a_deletion_is_a_copyright_deletion_only_when_its_comment_says_so(
    comment: str, cls: str
) -> None:
    answer = L.Answer(
        {"query": {"logevents": [_event(1, "delete", "delete", "2026-01-01T00:00:00Z", comment)]}},
        "x",
        "t",
    )
    assert L.classify_log(answer)[0] == cls


def test_a_move_without_a_target_is_refused() -> None:
    answer = L.Answer(
        {"query": {"logevents": [_event(1, "move", "move", "2026-01-01T00:00:00Z")]}}, "x", "t"
    )
    with pytest.raises(L.LivenessError, match="without a target"):
        L.classify_log(answer)


def test_a_truncated_log_without_a_deletion_or_move_is_refused(tmp_path: Path) -> None:
    commons = _commons()
    commons.truncate_logs = True
    with pytest.raises(L.LivenessError, match="truncated"):
        _sweep(tmp_path, commons, {"Never_logged.jpg": [1]})


@pytest.mark.parametrize(
    ("status", "text", "why"),
    [
        (404, "Not Found", "answered HTTP 404"),
        (200, "<html><body>Wikimedia Error</body></html>", "answered something that is not JSON"),
        (200, "[1, 2]", "answered a list, not an object"),
        (200, '{"batchcomplete": true}', "an answer without 'query'"),
    ],
)
def test_an_answer_that_is_not_a_query_answer_stops_the_sweep(
    tmp_path: Path, status: int, text: str, why: str
) -> None:
    commons = _commons()
    commons.raw_answers = [(status, text)]
    with pytest.raises(L.LivenessError, match=why):
        _sweep(tmp_path, commons, {"Alive_one.jpg": [1]})


def test_a_line_left_without_a_known_class_stops_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(L, "classify_log", lambda answer: ("vanished", None))
    with pytest.raises(L.LivenessError, match="left without a class"):
        _sweep(tmp_path, _commons(), {"Never_logged.jpg": [1]})


def test_a_file_without_a_pixel_size_is_a_page_without_file(tmp_path: Path) -> None:
    commons = _commons()
    # Commons answers width 0 and height 0 for a file that has no pixel size (audio)
    commons.files["File:Chant.ogg"] = {**_upload("Chant.ogg"), "width": 0, "height": 0}
    lines, _, _ = _sweep(tmp_path, commons, {"Chant.ogg": [1]})
    assert lines["Chant.ogg"]["class"] == L.PAGE_WITHOUT_FILE
    assert lines["Chant.ogg"]["width"] is None


def test_a_move_target_that_is_missing_too_is_stored_as_missing(tmp_path: Path) -> None:
    commons = _commons()
    del commons.files["File:Forum Romanum - panoramio (3).jpg"]
    lines, _, _ = _sweep(tmp_path, commons, {"-_panoramio_(1931).jpg": [16]})
    target = lines["-_panoramio_(1931).jpg"]["move_target"]
    assert target["class"] == "missing" and target["url"] is None


def test_a_title_the_answer_does_not_mention_stops_the_sweep(tmp_path: Path) -> None:
    commons = _commons()
    commons.drop_titles = {"File:Alive_one.jpg"}
    with pytest.raises(L.LivenessError, match="no page for 'File:Alive_one.jpg'"):
        _sweep(tmp_path, commons)


def test_the_sweep_never_asks_for_more_titles_than_the_api_answers(tmp_path: Path) -> None:
    names = {f"Alive_one_{i:03d}.jpg": [i] for i in range(120)}
    commons = _commons()
    commons.files.update(
        {f"File:Alive one {i:03d}.jpg": _upload(f"Alive one {i:03d}.jpg") for i in range(120)}
    )
    lines, _, _ = _sweep(tmp_path, commons, names)
    assert {line["class"] for line in lines.values()} == {L.LIVE}
    asked = [len(r["titles"][0].split("|")) for r in commons.requests if "titles" in r]
    assert asked == [50, 50, 20]
    # a 51-title batch is truncated by Commons, and the sweep refuses to read it as complete
    with (
        Fetcher(tmp_path / "c2", workers=1, transport=httpx.MockTransport(commons)) as fetcher,
        pytest.raises(L.LivenessError, match="no page for"),
    ):
        L.ask_pages(
            fetcher, [f"File:Alive_one_{i:03d}.jpg" for i in range(51)], ns="t", pace=L.Pace(0)
        )


def test_a_refused_long_uri_is_asked_again_in_halves(tmp_path: Path) -> None:
    commons = _commons()
    long_names = {("Alive_one_" + "x" * 200 + f"_{i}.jpg"): [i] for i in range(8)}
    commons.files.update({_normalise(f"File:{n}"): _upload(n) for n in long_names})
    commons.max_uri = 1200
    lines, _, _ = _sweep(tmp_path, commons, long_names)
    assert {line["class"] for line in lines.values()} == {L.LIVE}
    asked = [len(r["titles"][0].split("|")) for r in commons.requests if "titles" in r]
    assert max(asked) < 8  # the 8-title request was refused (414) and split


def test_a_maxlag_answer_is_asked_again_past_the_cache_and_a_persistent_one_stops(
    tmp_path: Path,
) -> None:
    commons = _commons()
    commons.maxlag_answers = 1
    lines, pace, clock = _sweep(tmp_path, commons, {"Alive_one.jpg": [1]})
    assert lines["Alive_one.jpg"]["class"] == L.LIVE
    assert len(commons.requests) == 2  # the cached maxlag answer was asked past, not re-read
    assert any(s >= L.ERROR_BACKOFF_S for s in clock.slept)
    commons.maxlag_answers = L.MAX_ATTEMPTS
    with pytest.raises(L.LivenessError, match="refused 3 times: maxlag"):
        _sweep(tmp_path / "second", commons, {"Alive_one.jpg": [1]})


def test_requests_are_paced_and_a_resumed_run_costs_no_request(tmp_path: Path) -> None:
    commons = _commons()
    lines, pace, clock = _sweep(tmp_path, commons)
    requests = len(commons.requests)
    assert pace.network_requests == requests
    assert sum(clock.slept) == pytest.approx(requests - 1)  # every gap after the first is 1 s
    again, pace2, clock2 = _sweep(tmp_path, commons)
    assert again == lines
    assert len(commons.requests) == requests and pace2.network_requests == 0 and clock2.slept == []


def test_the_pace_counts_from_the_start_of_a_request_and_the_deadline_stops_the_run(
    tmp_path: Path,
) -> None:
    clock = Clock()
    commons = _commons()

    def slow(request: httpx.Request) -> httpx.Response:
        clock.now += 0.4  # a request that takes 0.4 s leaves 0.6 s to wait, not 1 s
        return commons(request)

    pace = L.Pace(1.0, clock=clock, sleep=clock.sleep)
    with Fetcher(tmp_path / "cache", workers=1, transport=httpx.MockTransport(slow)) as fetcher:
        L.sweep({"Alive_one.jpg": [1], "Copyvio.jpg": [2]}, fetcher, ns="t", pace=pace)
    assert pace.network_requests == 2 and clock.slept == [pytest.approx(0.6)]
    late = L.Pace(1.0, deadline_s=0.5, clock=clock, sleep=clock.sleep)
    clock.now += 1.0
    with (
        Fetcher(tmp_path / "cache2", workers=1, transport=httpx.MockTransport(commons)) as fetcher,
        pytest.raises(L.LivenessError, match="deadline has passed after 0 network requests"),
    ):
        L.sweep({"Alive_one.jpg": [1]}, fetcher, ns="t", pace=late)


def test_every_request_carries_the_etiquette(tmp_path: Path) -> None:
    commons = _commons()
    _sweep(tmp_path, commons)
    assert commons.requests and all(r["maxlag"] == ["5"] for r in commons.requests)
    assert all(r["redirects"] == ["1"] for r in commons.requests if "titles" in r)


class StubSnapshot:
    """The two tables `referenced_files` reads. Unknown tables are refused, as Snapshot does."""

    def __init__(self, sites: list[dict[str, Any]], images: list[dict[str, Any]]) -> None:
        self.sites = sites
        self._images = images

    def rows(self, table: str) -> list[dict[str, Any]]:
        if table != "wiki_images":
            raise SnapshotError(f"unknown table {table!r}")
        return self._images


def test_only_curated_rows_with_a_commons_identity_are_referenced() -> None:
    snap = StubSnapshot(
        [
            {"id": "s1", "source_id": "ancient_nerds"},
            {"id": "s2", "source_id": "list_inscriptions"},
        ],
        [
            {
                "id": 3,
                "site_id": "s1",
                "original_url": f"{UPLOAD}/a/ab/Foo.jpg",
                "commons_page_url": None,
            },
            {
                "id": 1,
                "site_id": "s1",
                "original_url": None,
                "commons_page_url": "https://commons.wikimedia.org/wiki/File%3AFoo.jpg",
            },
            {
                "id": 2,
                "site_id": "s2",
                "original_url": f"{UPLOAD}/a/ab/Bar.jpg",
                "commons_page_url": None,
            },
            {
                "id": 4,
                "site_id": "s1",
                "original_url": "/data/images/wiki/x/y.webp",
                "commons_page_url": None,
            },
        ],
    )
    assert L.referenced_files(snap) == {"Foo.jpg": [1, 3]}


def test_the_store_round_trips_and_refuses_a_damaged_line(tmp_path: Path) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    summary = L.write_store(tmp_path / "store", list(lines.values()), {"snapshot_exported_at": "x"})
    assert summary["classes"][L.LIVE] == 1 and summary["files"] == len(FILES)
    assert summary["rows"] == sum(len(v) for v in FILES.values())
    back = L.load_store(tmp_path / "store" / "COMMONS.jsonl")
    assert [line["file"] for line in back] == sorted(FILES)
    not_live = L.load_store(tmp_path / "store" / "NOT_LIVE.jsonl")
    assert L.LIVE not in {line["class"] for line in not_live} and len(not_live) == len(FILES) - 1
    assert L.line_sha256(back[0]) == L.line_sha256(lines[back[0]["file"]])
    damaged = tmp_path / "damaged.jsonl"
    damaged.write_text(json.dumps({**back[0], "class": "gone"}) + "\n", encoding="utf-8")
    with pytest.raises(L.LivenessError, match="unknown class"):
        L.load_store(damaged)
    damaged.write_text(
        json.dumps({k: v for k, v in back[0].items() if k != "log"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(L.LivenessError, match="keys differ"):
        L.load_store(damaged)


def test_recheck_names_a_vanished_entry_a_newer_entry_and_a_dead_move_target(
    tmp_path: Path,
) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    assert _recheck(tmp_path / "a", _commons(), list(lines.values())) == []
    changed = _commons()
    changed.logs["File:Copyvio.jpg"] = []
    changed.logs["File:Deletion request.jpg"].append(
        _event(99, "move", "move", "2026-09-20T00:00:00Z", target_title="File:Y.jpg")
    )
    del changed.files["File:Forum Romanum - panoramio (3).jpg"]
    problems = _recheck(tmp_path / "b", changed, list(lines.values()))
    assert any("Copyvio.jpg: log entry 9 is no longer" in p for p in problems)
    assert any("Deletion_request.jpg: a newer entry 99" in p for p in problems)
    assert any(
        "move target 'File:Forum Romanum - panoramio (3).jpg' is missing" in p for p in problems
    )


def _recheck(root: Path, commons: FakeCommons, lines: list[dict[str, Any]]) -> list[str]:
    with Fetcher(root, workers=1, transport=httpx.MockTransport(commons)) as fetcher:
        return L.recheck(lines, fetcher, ns="recheck", pace=L.Pace(0))


def test_recheck_names_a_restored_copyvio_and_a_file_uploaded_anew(tmp_path: Path) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    later = _commons()
    # a copyvio restored after a VRT permission: the file answers imageinfo again, the log gains
    # a restore newer than the stored deletion
    later.files["File:Copyvio.jpg"] = _upload("Copyvio.jpg")
    later.logs["File:Copyvio.jpg"].append(
        _event(42, "delete", "restore", "2026-09-24T09:00:00Z", "VRT ticket")
    )
    # a deleted file uploaded again under its old name
    later.files["File:Deletion request.jpg"] = _upload("Deletion request.jpg")
    later.logs["File:Deletion request.jpg"].append(
        _event(43, "upload", "upload", "2026-09-25T10:00:00Z", "own work, new photo")
    )
    problems = _recheck(tmp_path / "later", later, list(lines.values()))
    assert any(
        "Copyvio.jpg: Commons answers 'File:Copyvio.jpg' as live again" in p for p in problems
    )
    assert any("Copyvio.jpg: a newer entry 42 (delete/restore" in p for p in problems)
    assert any(
        "Deletion_request.jpg: Commons answers" in p and "as live again" in p for p in problems
    )
    assert any("Deletion_request.jpg: a newer entry 43 (upload/upload" in p for p in problems)


def test_recheck_asks_imageinfo_again_even_when_the_log_says_nothing_new(tmp_path: Path) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    later = _commons()
    later.files["File:Copyvio.jpg"] = _upload("Copyvio.jpg")  # live again, the log unchanged
    problems = _recheck(tmp_path / "later", later, list(lines.values()))
    assert problems == [
        "Copyvio.jpg: Commons answers 'File:Copyvio.jpg' as live again - it is no longer missing"
    ]


def test_recheck_names_an_upload_newer_than_the_deletion_while_the_file_is_still_missing(
    tmp_path: Path,
) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    later = _commons()
    later.logs["File:Copyvio.jpg"].append(_event(44, "upload", "overwrite", "2026-09-24T09:00:00Z"))
    problems = _recheck(tmp_path / "later", later, list(lines.values()))
    assert problems == [
        "Copyvio.jpg: a newer entry 44 (upload/overwrite, 2026-09-24T09:00:00Z) is in the log after 9"
    ]


def test_the_recheck_command_exits_4_on_a_problem_and_0_on_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines, _, _ = _sweep(tmp_path, _commons())
    store = tmp_path / "store"
    L.write_store(store, list(lines.values()), {"snapshot_exported_at": "x"})
    answers = {"commons": _commons()}
    monkeypatch.setattr(
        L,
        "Fetcher",
        lambda cache, workers: Fetcher(
            cache, workers=workers, transport=httpx.MockTransport(answers["commons"])
        ),
    )

    def argv(cache: str) -> list[str]:
        # the command's cache namespace is dated to the second: a separate cache per run
        return [
            "recheck",
            "--store",
            str(store),
            "--cache",
            str(tmp_path / cache),
            "--interval",
            "0",
        ]

    assert L.main(argv("c1")) == 0
    assert json.loads((store / "RECHECK.json").read_text(encoding="utf-8"))["problems"] == []
    answers["commons"] = _commons()
    answers["commons"].files["File:Copyvio.jpg"] = _upload("Copyvio.jpg")
    assert L.main(argv("c2")) == 4
    assert json.loads((store / "RECHECK.json").read_text(encoding="utf-8"))["problems"]


@needs_snapshot
def test_the_seven_files_found_dead_on_2026_09_22_are_referenced_by_the_snapshot() -> None:
    from census.snapshot import Snapshot

    files = L.referenced_files(Snapshot(SNAPSHOT))
    assert len(files) == 46_070
    for name, image_id in (
        ("Athens_Acropolis_Stoa_of_Eumenes_II_(28437052525).jpg", 80453),
        ("Athens_Acropolis_Sanctuary_of_Dionysos_Eleuthereus_(28154647030).jpg", 97070),
        ("Dedan_tomb_1.jpg", 87351),
        ("Ddan_tomb_2.jpg", 87352),
        ("Infopanel_hardloopbaan_Olympia.jpg", 70233),
        ("A_Minecraft_Movie_McDonald's_promotion_-_3_May_2025.jpg", 107331),
        ("-_panoramio_(1931).jpg", 75145),
    ):
        assert image_id in files[name]


STORE = REPO / "output" / "remediation" / "gallery_audit" / "liveness-2026-09-23"


def test_the_versioned_liveness_evidence_is_the_store_its_summary_describes() -> None:
    summary = json.loads((STORE / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["not_live_sha256"] == L.text_sha256(STORE / "NOT_LIVE.jsonl")
    not_live = L.load_store(STORE / "NOT_LIVE.jsonl")
    counted = {cls: n for cls, n in summary["classes"].items() if cls != L.LIVE}
    assert {cls: sum(1 for line in not_live if line["class"] == cls) for cls in counted} == counted
    assert summary["files"] == 46_070 and summary["classes"][L.LIVE] == 46_059
    if (STORE / "COMMONS.jsonl").exists():  # the full store is local-only (gitignored)
        assert summary["commons_sha256"] == L.text_sha256(STORE / "COMMONS.jsonl")


# ------------------------------------------------------------------------------ the write (chunk)
#: Three sites: A keeps a live image after its deleted hero goes, B loses its only image, C's image
#: was renamed without a redirect.
SA = "00000000-0000-4000-8000-00000000000a"
SB = "00000000-0000-4000-8000-00000000000b"
SC = "00000000-0000-4000-8000-00000000000c"
CHUNK_FILES = {
    "Alive_one.jpg": [11, 12],
    "Copyvio.jpg": [14],
    "Deletion_request.jpg": [15],
    "-_panoramio_(1931).jpg": [16],
}
STORE_POINTER = "output/remediation/gallery_audit/liveness-2026-09-23/NOT_LIVE.jsonl"


def _image(image_id: int, site: str, name: str, **kw: Any) -> dict[str, Any]:
    row = {
        "id": image_id,
        "site_id": site,
        "is_excluded": False,
        "is_hero": False,
        "original_url": f"{UPLOAD}/a/ab/{name}",
        "commons_page_url": f"https://commons.wikimedia.org/wiki/File%3A{name}",
        "_tier": "C",
    }
    row.update(kw)
    return row


CHUNK_ROWS = {
    SA: [_image(11, SA, "Alive_one.jpg"), _image(14, SA, "Copyvio.jpg", is_hero=True)],
    SB: [_image(15, SB, "Deletion_request.jpg")],
    SC: [_image(12, SC, "Alive_one.jpg"), _image(16, SC, "-_panoramio_%281931%29.jpg")],
}


def _chunk_store(tmp_path: Path, name: str = "liveness-2026-09-23") -> tuple[Path, list[Any]]:
    """A swept store (the fake Commons), its L1/L2 plan (`decide.plan_liveness`) and a clean
    recheck - what `chunk` reads."""
    from gallery_audit import decide
    from gallery_audit.planned import write_plan

    lines, _, _ = _sweep(tmp_path, _commons(), CHUNK_FILES)
    store = tmp_path / name
    L.write_store(store, list(lines.values()), {"snapshot_exported_at": "x"})
    planned, _ = decide.plan_liveness(list(lines.values()), CHUNK_ROWS, {})
    write_plan(store / "PLANNED.jsonl", planned)
    (store / "RECHECK.json").write_text(json.dumps({"checked": 3, "problems": []}), "utf-8")
    return store, planned


def _changes(store: Path, planned: list[Any]) -> list[Any]:
    return L.plan_changes(planned, L.load_store(store / "NOT_LIVE.jsonl"), store)


def test_the_chunk_carries_every_planned_row_exactly_as_planned(tmp_path: Path) -> None:
    store, planned = _chunk_store(tmp_path)
    changes = _changes(store, planned)
    assert [(c.row_key, c.column, c.old_value, c.new_value, c.rule) for c in changes] == [
        (
            "16",
            "commons_page_url",
            "https://commons.wikimedia.org/wiki/File%3A-_panoramio_%281931%29.jpg",
            "https://commons.wikimedia.org/wiki/File%3AForum%20Romanum%20-%20panoramio%20%283%29.jpg",
            "L2",
        ),
        (
            "16",
            "original_url",
            f"{UPLOAD}/a/ab/-_panoramio_%281931%29.jpg",
            f"{UPLOAD}/a/ab/Forum_Romanum_-_panoramio_(3).jpg",
            "L2",
        ),
        ("14", "is_excluded", "false", "true", "L1"),
        ("14", "is_hero", "true", "false", "L1"),
        ("15", "is_excluded", "false", "true", "L1"),
    ]
    by_key = {(c.row_key, c.column): c for c in changes}
    assert by_key[("14", "is_excluded")].reason == (
        "Commons deleted File:Copyvio.jpg as a copyright violation (log 9, 2026-09-14T08:22:32Z); "
        "the row is excluded"
    )
    assert by_key[("14", "is_hero")].reason.endswith("an excluded row cannot stay the site's hero")
    assert (
        "for a stated reason other than copyright (log 8," in by_key[("15", "is_excluded")].reason
    )
    assert by_key[("16", "original_url")].reason == (
        "Commons renamed File:-_panoramio_(1931).jpg to File:Forum Romanum - panoramio (3).jpg "
        "without a redirect (log 7, 2026-09-16T00:59:40Z); original_url points at the live target"
    )
    for change, row in zip(changes, planned, strict=True):
        (evidence,) = change.evidence
        # every planned pointer, unchanged, plus where it points
        assert {k: evidence[k] for k in row.evidence} == row.evidence
        assert evidence["store"] == STORE_POINTER and evidence["source"]
        L.CW.validate_change(change)


def test_a_planned_row_whose_store_line_does_not_state_it_is_refused(tmp_path: Path) -> None:
    store, planned = _chunk_store(tmp_path)
    exclude = next(p for p in planned if p.key == 14 and p.column == "is_excluded")
    for evidence, says in (
        ({**exclude.evidence, "liveness_sha256": "00" * 32}, "names no line"),
        ({**exclude.evidence, "class": L.DELETED_OTHER}, "(class)"),
        ({**exclude.evidence, "logid": 10}, "(logid)"),
        ({**exclude.evidence, "commons_file": "Other.jpg"}, "(commons_file)"),
        ({**exclude.evidence, "rule": "L2"}, "(rule)"),
    ):
        with pytest.raises(L.LivenessError, match=re.escape(says)):
            _changes(store, [replace(exclude, evidence=evidence)])
    with pytest.raises(L.LivenessError, match="does not reference the row"):
        _changes(store, [replace(exclude, key=11)])
    moved = next(p for p in planned if p.column == "original_url")
    as_exclusion = replace(
        moved,
        rule="L1",
        role="exclude",
        column="is_excluded",
        old=False,
        new=True,
        evidence={**moved.evidence, "rule": "L1"},
    )
    with pytest.raises(L.LivenessError, match="does not allow exclude"):
        _changes(store, [as_exclusion])


def test_a_row_its_role_does_not_write_or_a_value_the_store_does_not_give_is_refused(
    tmp_path: Path,
) -> None:
    store, planned = _chunk_store(tmp_path)
    exclude = next(p for p in planned if p.key == 14 and p.column == "is_excluded")
    with pytest.raises(L.LivenessError, match="does not write is_hero"):
        _changes(store, [replace(exclude, column="is_hero")])
    with pytest.raises(L.LivenessError, match="exclude is"):
        _changes(store, [replace(exclude, old=True, new=False)])
    with pytest.raises(L.LivenessError, match="neither a boolean"):
        _changes(store, [replace(exclude, old=0, new=1)])
    moved = next(p for p in planned if p.column == "original_url")
    with pytest.raises(L.LivenessError, match="is not the move target"):
        _changes(store, [replace(moved, new=f"{UPLOAD}/a/ab/Somewhere_else.jpg")])
    promote = replace(
        exclude,
        key=11,
        column="is_hero",
        old=False,
        new=True,
        role="hero-promote",
        evidence={"rule": "L1", "replacement_rule": "hero_repair"},
    )
    with pytest.raises(L.LivenessError, match="without the hero L1 took"):
        _changes(store, [replace(promote, site_id=SB)])
    # beside the drop on its own site it passes, and cites the hero repair's rule
    drop = next(p for p in planned if p.column == "is_hero")
    changes = _changes(store, [drop, promote])
    assert changes[1].reason.startswith("L1 took the site's hero; hero_repair chose this row")


def test_the_chunk_is_cut_only_from_a_store_whose_recheck_found_nothing(tmp_path: Path) -> None:
    store, _ = _chunk_store(tmp_path)
    lines = L.load_store(store / "NOT_LIVE.jsonl")
    L.require_recheck(store, lines)
    for report in (
        {"checked": 3, "problems": ["Copyvio.jpg: back"]},
        {"checked": 2, "problems": []},
    ):
        (store / "RECHECK.json").write_text(json.dumps(report), "utf-8")
        with pytest.raises(L.LivenessError, match="not a clean recheck"):
            L.require_recheck(store, lines)
    (store / "RECHECK.json").unlink()
    with pytest.raises(L.LivenessError, match="run `liveness.py recheck`"):
        L.require_recheck(store, lines)


def test_the_lane_journals_under_the_stores_date() -> None:
    lane = L.chunk_lane(Path("x") / "liveness-2026-10-01")
    assert (lane.name, lane.stamp, lane.test_id, lane.confidence) == (
        "img-liveness",
        "img-liveness-2026-10-01",
        "T09/liveness",
        "authoritative",
    )
    with pytest.raises(L.LivenessError, match="not a liveness store"):
        L.chunk_lane(Path("attribution-2026-09-23"))


def _production(rows_by_site: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {"id": r["id"], "site_id": r["site_id"], "is_excluded": r["is_excluded"]}
        for rows in rows_by_site.values()
        for r in rows
    ]


def test_the_sites_left_without_a_live_image_are_computed_from_production(tmp_path: Path) -> None:
    store, planned = _chunk_store(tmp_path)
    changes = _changes(store, planned)
    assert L.emptied_sites(changes, _production(CHUNK_ROWS)) == [SB]
    # a NULL is_excluded is live; a site that had no live image before loses nothing
    held = [*_production(CHUNK_ROWS), {"id": 99, "site_id": SB, "is_excluded": None}]
    assert L.emptied_sites(changes, held) == []
    already = [r if r["id"] != 15 else {**r, "is_excluded": True} for r in _production(CHUNK_ROWS)]
    assert L.emptied_sites(changes, already) == []
    # a planned row production does not hold on the planned site stops the chunk
    moved = [r if r["id"] != 14 else {**r, "site_id": SB} for r in _production(CHUNK_ROWS)]
    with pytest.raises(L.LivenessError, match="is not a row of site"):
        L.emptied_sites(changes, moved)


def test_the_command_emits_only_when_the_named_sites_are_exactly_the_emptied_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store, _ = _chunk_store(tmp_path)
    sent: list[str] = []

    def read_rows(sql: str) -> list[dict[str, Any]]:
        sent.append(sql)
        assert sql.startswith("SELECT row_to_json(t) FROM (\n  SELECT w.id, w.site_id::text")
        assert set(re.findall(r"'([0-9a-f-]{36})'::uuid", sql)) == {SA, SB, SC}
        return _production(CHUNK_ROWS)

    monkeypatch.setattr(L.CW.pv, "read_rows", read_rows)
    argv = ["chunk", "--store", str(store)]
    # a store whose recheck found a problem is not cut into a chunk, whatever is named
    recheck = store / "RECHECK.json"
    clean = recheck.read_text(encoding="utf-8")
    recheck.write_text(json.dumps({"checked": 3, "problems": ["Copyvio.jpg: back"]}), "utf-8")
    assert L.main([*argv, "--may-empty", SB]) == 2
    assert "not a clean recheck" in capsys.readouterr().err and not sent
    recheck.write_text(clean, "utf-8")
    assert L.main(argv) == 2
    assert f"the plan leaves ['{SB}'] without a live image" in capsys.readouterr().err
    assert L.main([*argv, "--may-empty", SB, "--may-empty", SA]) == 2
    assert not (store / "chunk-001").exists()
    assert L.main([*argv, "--may-empty", SB]) == 0
    chunk = L.CW.check_delivered(store / "chunk-001")
    assert chunk.lane == L.chunk_lane(store) and chunk.may_empty == frozenset({SB})
    assert chunk.run_stamp == "img-liveness-2026-09-23-001" and len(chunk.changes) == 5
    assert len(sent) == 3


def _row_order(change: Any) -> tuple[str, str, str, int]:
    return (change.site_id, change.table, change.column, int(change.row_key))


def test_the_delivered_liveness_chunk_is_the_plan_of_the_store() -> None:
    """chunk-001 is what `chunk` makes of the versioned store: the 9 planned rows, and Dedan the
    one site it may empty (production, read 2026-09-23: its two rows are both deleted files)."""
    from gallery_audit.planned import read_plan

    chunk = L.CW.check_delivered(STORE / "chunk-001")
    assert chunk.lane == L.chunk_lane(STORE)
    planned = read_plan(STORE / "PLANNED.jsonl")
    made = L.plan_changes(planned, L.load_store(STORE / "NOT_LIVE.jsonl"), STORE)
    assert sorted(chunk.changes, key=_row_order) == sorted(made, key=_row_order)
    assert chunk.may_empty == frozenset({"9a9a0dca-52c8-44c2-94f6-adb655db17dd"})
    assert sorted((c.row_key, c.column, c.old_value, c.new_value) for c in chunk.changes) == [
        ("107331", "is_excluded", "false", "true"),
        ("70233", "is_excluded", "false", "true"),
        (
            "75145",
            "commons_page_url",
            "https://commons.wikimedia.org/wiki/File%3A-%20panoramio%20%281931%29.jpg",
            "https://commons.wikimedia.org/wiki/File%3AForum%20Romanum%20-%20panoramio%20%283%29.jpg",
        ),
        (
            "75145",
            "original_url",
            "https://upload.wikimedia.org/wikipedia/commons/d/db/-_panoramio_%281931%29.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/5/5f/Forum_Romanum_-_panoramio_%283%29.jpg",
        ),
        ("80453", "is_excluded", "false", "true"),
        ("87351", "is_excluded", "false", "true"),
        ("87352", "is_excluded", "false", "true"),
        ("87352", "is_hero", "true", "false"),
        ("97070", "is_excluded", "false", "true"),
    ]

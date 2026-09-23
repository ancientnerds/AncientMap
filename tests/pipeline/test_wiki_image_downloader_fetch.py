# SPDX-License-Identifier: AGPL-3.0-only
"""The downloader's Commons fetch rule: fixed buckets, never an upscale, never a silent failure.

Until 2026-09-23 `download_image` asked Commons for `/800px-` (hero) and `/1600px-` (gallery)
thumbnails. Measured that day with the census User-Agent: both widths answer HTTP 400 - Wikimedia
serves only the fixed buckets 20/40/60/120/250/330/500/960/1280/1920/3840 - so every new download
failed, and it failed silently (`logger.debug` and `return None`). A bucket wider than the
original is served upscaled (a 327x800 original came back from the 1920 bucket as 1920x4697).

The rule now: fetch the original when it is at most FETCH_BUCKET (1920) px wide, else the 1920
bucket; downscale locally to LOCAL_MAX_WIDTH (1600); refuse anything wider than the original;
write with O_EXCL; raise `DownloadError` for every failure.

No network: the download client is an `httpx.Client` over an `httpx.MockTransport`, which parses
the real request the code builds, so a wrong URL is a wrong answer here too. The site run
(`process_site`) talks to a Wikipedia transport that answers in the shape measured live on
2026-09-23 (media-list titles with underscores, imageinfo keyed by the normalised title, urls with
`?utm_` parameters) and to a fake session that, like SQLAlchemy 2, refuses plain SQL strings.
"""

from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy.exc import ArgumentError, IntegrityError, OperationalError
from sqlalchemy.sql.elements import TextClause

from pipeline import wiki_image_downloader as D

ORIGINAL = "https://upload.wikimedia.org/wikipedia/commons/8/8b/Gizeh-Stele_du_reve.jpg"
BUCKET = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8b/Gizeh-Stele_du_reve.jpg"
    "/1920px-Gizeh-Stele_du_reve.jpg"
)


def _jpeg(width: int, height: int) -> bytes:
    """A real JPEG with some structure, so it is well above the 1,000-byte floor."""
    img = Image.radial_gradient("L").resize((width, height)).convert("RGB")
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _serve(monkeypatch, routes: dict[str, httpx.Response | Exception]) -> list[str]:
    """Answer each exact URL with its response; record every URL asked."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        asked.append(url)
        answer = routes.get(url)
        if answer is None:
            return httpx.Response(404, text="not routed")
        if isinstance(answer, Exception):
            raise answer
        return answer

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(D, "_download_client", client)
    return asked


def _image(data: bytes) -> httpx.Response:
    return httpx.Response(200, content=data, headers={"content-type": "image/jpeg"})


def _stored(path: Path) -> tuple[str, tuple[int, int]]:
    with Image.open(path) as img:
        return img.format, img.size


# --------------------------------------------------------------------------------------
# the contract
# --------------------------------------------------------------------------------------


def test_the_bucket_list_is_the_one_commons_serves():
    assert D.COMMONS_BUCKETS == (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)
    # the two widths the old constants asked for are exactly the ones Commons refuses
    assert 800 not in D.COMMONS_BUCKETS and 1600 not in D.COMMONS_BUCKETS
    assert D.LOCAL_MAX_WIDTH == 1600
    assert D.FETCH_BUCKET in D.COMMONS_BUCKETS
    assert D.FETCH_BUCKET == min(b for b in D.COMMONS_BUCKETS if b >= D.LOCAL_MAX_WIDTH)
    assert not hasattr(D, "THUMB_WIDTH") and not hasattr(D, "GALLERY_WIDTH")


@pytest.mark.parametrize("width", [327, 1200, 1600, 1920])
def test_an_original_no_wider_than_the_bucket_is_fetched_itself(width):
    """Every bucket that is >= LOCAL_MAX_WIDTH would be an upscale of these originals."""
    assert D.fetch_plan(ORIGINAL, width) == (ORIGINAL, None)


@pytest.mark.parametrize("width", [1921, 4000, 12000])
def test_a_wider_original_is_fetched_as_the_1920_bucket(width):
    assert D.fetch_plan(ORIGINAL, width) == (BUCKET, 1920)


def test_a_local_wiki_upload_gets_its_own_thumb_path():
    url = "https://upload.wikimedia.org/wikipedia/en/a/ab/Temple_%28north%29.png"
    assert D.fetch_plan(url, 3000) == (
        "https://upload.wikimedia.org/wikipedia/en/thumb/a/ab/Temple_%28north%29.png"
        "/1920px-Temple_%28north%29.png",
        1920,
    )


@pytest.mark.parametrize(
    ("url", "width", "reason"),
    [
        ("https://example.org/wikipedia/commons/8/8b/X.jpg", 3000, "not an upload.wikimedia.org"),
        ("http://upload.wikimedia.org/wikipedia/commons/8/8b/X.jpg", 3000, "not an upload"),
        (BUCKET, 3000, "not the path of an upload original"),
        (ORIGINAL, None, "the original's width is None"),
        (ORIGINAL, 0, "the original's width is 0"),
        (ORIGINAL, True, "the original's width is True"),
        (f"{ORIGINAL}?utm_source=en.wikipedia.org&utm_campaign=imageinfo", 1200, "no query"),
        (f"{ORIGINAL}#x", 1200, "no query or fragment"),
        ("https://upload.wikimedia.org/wikipedia/commons/8/8b/Scan.tif", 5000, "no thumbnail"),
    ],
)
def test_what_has_no_valid_fetch_is_refused_by_name(url, width, reason):
    with pytest.raises(D.DownloadError) as exc:
        D.fetch_plan(url, width)
    assert reason in str(exc.value)


def test_the_stored_size_is_capped_and_never_enlarged():
    assert D.stored_size(1920, 1080) == (1600, 900)
    assert D.stored_size(1200, 900) == (1200, 900)
    assert D.stored_size(1600, 400) == (1600, 400)
    assert D.stored_size(12000, 1) == (1600, 1)


# --------------------------------------------------------------------------------------
# the download
# --------------------------------------------------------------------------------------


def test_a_small_original_is_stored_at_its_own_size(tmp_path, monkeypatch):
    asked = _serve(monkeypatch, {ORIGINAL: _image(_jpeg(1200, 800))})
    dest = tmp_path / "abcdef12" / "Stele.webp"
    result = D.download_image(ORIGINAL, dest, 1200)
    assert asked == [ORIGINAL]
    assert _stored(dest) == ("WEBP", (1200, 800))
    assert (result.width, result.height) == (1200, 800)
    assert result.fetched_bucket is None and result.fetch_url == ORIGINAL
    assert result.file_size == dest.stat().st_size


def test_a_large_original_arrives_as_the_bucket_and_is_stored_at_1600(tmp_path, monkeypatch):
    asked = _serve(monkeypatch, {BUCKET: _image(_jpeg(1920, 1080))})
    dest = tmp_path / "hero.webp"
    result = D.download_image(ORIGINAL, dest, 5184)
    assert asked == [BUCKET]
    assert _stored(dest) == ("WEBP", (1600, 900))
    assert (result.width, result.height, result.fetched_bucket) == (1600, 900, 1920)


def test_an_image_wider_than_its_original_is_refused_as_an_upscale(tmp_path, monkeypatch):
    """What an oversize bucket does: the metadata says 1,000 px, the answer has 1,920."""
    _serve(monkeypatch, {ORIGINAL: _image(_jpeg(1920, 1080))})
    dest = tmp_path / "x.webp"
    with pytest.raises(D.DownloadError) as exc:
        D.download_image(ORIGINAL, dest, 1000)
    assert "wider than the 1000 px original" in str(exc.value)
    assert not dest.exists()


def test_a_commons_400_is_an_error_and_not_a_skip(tmp_path, monkeypatch):
    """The old code logged this at debug level and returned None - every 800/1600 request."""
    _serve(monkeypatch, {BUCKET: httpx.Response(400, text="<html>Wikimedia Error</html>")})
    with pytest.raises(D.DownloadError) as exc:
        D.download_image(ORIGINAL, tmp_path / "x.webp", 4000)
    assert exc.value.reason == "HTTP 400"
    assert exc.value.url == BUCKET


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            httpx.Response(200, text="<html/>", headers={"content-type": "text/html"}),
            "not an image",
        ),
        (httpx.Response(200, content=b"x" * 10, headers={"content-type": "image/jpeg"}), "bytes"),
        (
            httpx.Response(200, content=b"\x00" * 5000, headers={"content-type": "image/jpeg"}),
            "not a decodable image",
        ),
        (httpx.ConnectError("reset"), "no response"),
    ],
)
def test_every_other_failure_raises_and_writes_nothing(tmp_path, monkeypatch, answer, reason):
    """The old code saved undecodable bytes as a `.webp` with height 0."""
    _serve(monkeypatch, {ORIGINAL: answer})
    dest = tmp_path / "x.webp"
    with pytest.raises(D.DownloadError) as exc:
        D.download_image(ORIGINAL, dest, 1200)
    assert reason in str(exc.value)
    assert not dest.exists()


def test_an_answer_over_the_byte_limit_is_refused(tmp_path, monkeypatch):
    data = _jpeg(1200, 800)
    monkeypatch.setattr(D, "MAX_RAW_BYTES", len(data) - 1)
    _serve(monkeypatch, {ORIGINAL: _image(data)})
    dest = tmp_path / "x.webp"
    with pytest.raises(D.DownloadError, match="over the limit"):
        D.download_image(ORIGINAL, dest, 1200)
    assert not dest.exists()


def test_a_429_is_left_to_the_caller_to_retry(tmp_path, monkeypatch):
    _serve(monkeypatch, {ORIGINAL: httpx.Response(429, headers={"retry-after": "30"})})
    with pytest.raises(D.RateLimitedError) as exc:
        D.download_image(ORIGINAL, tmp_path / "x.webp", 1200)
    assert exc.value.retry_after == 30.0


def test_an_existing_file_is_never_overwritten(tmp_path, monkeypatch):
    _serve(monkeypatch, {ORIGINAL: _image(_jpeg(1200, 800))})
    dest = tmp_path / "hero.webp"
    dest.write_bytes(b"the file a page already serves")
    with pytest.raises(D.DownloadError) as exc:
        D.download_image(ORIGINAL, dest, 1200)
    assert "never overwritten" in str(exc.value)
    assert dest.read_bytes() == b"the file a page already serves"


# --------------------------------------------------------------------------------------
# the run names every failure
# --------------------------------------------------------------------------------------


def test_the_sequential_runner_returns_every_failure_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    other = "https://upload.wikimedia.org/wikipedia/commons/1/12/Gate.jpg"
    busy = "https://upload.wikimedia.org/wikipedia/commons/3/34/Busy.jpg"
    _serve(
        monkeypatch,
        {
            ORIGINAL: _image(_jpeg(1200, 800)),
            other: httpx.Response(404),
            busy: httpx.Response(429, headers={"retry-after": "1"}),
        },
    )
    tasks = [
        (0, {"title": "File:Stele.jpg"}, ORIGINAL, tmp_path / "a.webp", 1200),
        (1, {"title": "File:Gate.jpg"}, other, tmp_path / "b.webp", 1200),
        (2, {"title": "File:Busy.jpg"}, busy, tmp_path / "c.webp", 1200),
    ]
    results, failures = D.download_images_sequential(tasks)
    assert [(idx, r.width) for idx, _, _, r in results] == [(0, 1200)]
    assert [(f.title, f.reason) for f in failures] == [
        ("File:Gate.jpg", "HTTP 404"),
        ("File:Busy.jpg", f"HTTP 429 in all {D.DOWNLOAD_RETRY_ROUNDS} rounds"),
    ]


def test_a_run_with_failures_exits_non_zero_and_lists_them(monkeypatch):
    failure = D.FailedDownload("File:Gate.jpg", "https://upload.wikimedia.org/x.jpg", "HTTP 404")
    monkeypatch.setattr(D, "run_downloader", lambda **kwargs: [failure])
    monkeypatch.setattr("sys.argv", ["wiki_image_downloader", "--site-id", "x"])
    with pytest.raises(SystemExit) as exc:
        D.main()
    assert exc.value.code == "1 image(s) could not be stored - listed above"


# --------------------------------------------------------------------------------------
# the site run: the metadata lookup, the rows, and every failure named
# --------------------------------------------------------------------------------------

SITE = "abcdef12-0000-4000-8000-000000000001"
SITE_ROW = {"id": SITE, "name": "Temple of Test", "source_url": "https://en.wikipedia.org/wiki/Temple_of_Test"}
GATE = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Temple_gate.jpg"
GATE_TITLE = "File:Temple_gate.jpg"  # the media-list spelling: underscores
UTM = "?utm_source=en.wikipedia.org&utm_campaign=imageinfo&utm_content=original"


def _media_list() -> dict[str, Any]:
    thumb = (
        "//thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Temple_gate.jpg/1280px-Temple_gate.jpg"
        "?utm_source=en.wikipedia.org&utm_campaign=parser&utm_content=thumbnail"
    )
    return {
        "items": [
            {
                "title": GATE_TITLE,
                "leadImage": True,
                "type": "image",
                "showInGallery": True,
                "srcset": [{"src": thumb, "scale": "1x"}],
            }
        ]
    }


def _imageinfo(titles: list[str]) -> dict[str, Any]:
    """The en.wikipedia answer for Commons files: normalised titles, `?utm_` urls (measured)."""
    info = {
        "width": 1200,
        "height": 800,
        "url": GATE + UTM,
        "extmetadata": {
            "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:Jane">Jane</a>'},
            "LicenseShortName": {"value": "CC BY-SA 4.0"},
        },
    }
    pages = {
        str(-1 - n): {
            "ns": 6,
            "title": title.replace("_", " "),
            "missing": "",
            "known": "",
            "imagerepository": "shared",
            "imageinfo": [info],
        }
        for n, title in enumerate(titles)
    }
    normalized = [{"from": t, "to": t.replace("_", " ")} for t in titles if "_" in t]
    return {"batchcomplete": "", "query": {"normalized": normalized, "pages": pages}}


def _wikipedia(monkeypatch) -> list[httpx.Request]:
    """en.wikipedia as the site run asks it: media-list, pageprops (no Wikidata item), imageinfo."""
    asked: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        url = request.url
        if url.path == "/api/rest_v1/page/media-list/Temple_of_Test":
            return httpx.Response(200, json=_media_list())
        assert (url.host, url.path) == ("en.wikipedia.org", "/w/api.php"), f"not asked: {url}"
        if url.params["prop"] == "pageprops":
            return httpx.Response(200, json={"query": {"pages": {"7": {"title": "Temple of Test"}}}})
        assert url.params["prop"] == "imageinfo", f"not asked: {url}"
        return httpx.Response(200, json=_imageinfo(url.params["titles"].split("|")))

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(D, "_http_client", client)
    return asked


class FakeDB:
    """The wiki_images rows of the site, the thumbnails written, and an insert that may fail."""

    def __init__(self, rows: list[dict[str, str]] | None = None) -> None:
        self.rows = [dict(r) for r in rows or []]
        self.inserted: list[D.WikiImage] = []
        self.thumbnails: dict[str, str] = {}
        self.fail_insert: Exception | None = None


class FakeSession:
    """What process_site does with a session - and SQLAlchemy 2's refusal of a plain string."""

    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self.pending: list[tuple[str, Any]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        if not isinstance(statement, TextClause):
            raise ArgumentError(
                f"Textual SQL expression {statement!r} should be explicitly declared as text()"
            )
        sql = " ".join(str(statement).split())
        if sql == "SELECT original_url, filename FROM wiki_images WHERE site_id = :sid":
            rows = [SimpleNamespace(**r) for r in self.db.rows if r["site_id"] == params["sid"]]
            return SimpleNamespace(fetchall=lambda: rows)
        if sql == "UPDATE unified_sites SET thumbnail_url = :url WHERE id = :sid":
            self.pending.append(("thumbnail", (params["sid"], params["url"])))
            return SimpleNamespace(rowcount=1)
        raise AssertionError(f"the fake session cannot run: {sql}")

    def add(self, obj: Any) -> None:
        assert isinstance(obj, D.WikiImage), obj
        self.pending.append(("row", obj))

    def commit(self) -> None:
        pending, self.pending = self.pending, []
        for kind, item in pending:
            if kind == "thumbnail":
                self.db.thumbnails[item[0]] = item[1]
                continue
            if self.db.fail_insert is not None:
                raise self.db.fail_insert
            if any(
                (r["site_id"], r["original_url"]) == (item.site_id, item.original_url)
                for r in self.db.rows
            ):
                raise IntegrityError(
                    "INSERT INTO wiki_images",
                    {},
                    Exception('duplicate key value violates unique constraint "uq_wiki_image_site_url"'),
                )
            self.db.rows.append(
                {"site_id": item.site_id, "original_url": item.original_url, "filename": item.filename}
            )
            self.db.inserted.append(item)

    def rollback(self) -> None:
        self.pending = []

    def close(self) -> None:
        pass


def _site_run(monkeypatch, tmp_path: Path, db: FakeDB) -> list[str]:
    """Everything process_site touches, offline; returns the download URLs asked."""
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    monkeypatch.setattr(D, "IMAGE_DIR", tmp_path)
    _wikipedia(monkeypatch)

    @contextmanager
    def get_session():  # the real one's shape: commit on exit, rollback and re-raise on error
        session = FakeSession(db)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(D, "get_session", get_session)
    return _serve(monkeypatch, {GATE: _image(_jpeg(1200, 800))})


def test_the_metadata_batch_answers_under_the_title_that_was_asked(monkeypatch):
    """Measured: keyed by the answer's own title, 12 of 12 media-list titles were missed."""
    _wikipedia(monkeypatch)
    got = D.fetch_image_metadata_batch([GATE_TITLE, "Temple gate.jpg"])
    assert set(got) == {GATE_TITLE, "File:Temple gate.jpg"}
    for meta in got.values():
        assert (meta["width"], meta["height"]) == (1200, 800)
        assert meta["original_url"] == GATE  # the ?utm_ query is parse_attribution's to strip


def test_an_underscore_media_list_title_is_stored_with_its_width_and_a_bare_url(
    tmp_path, monkeypatch
):
    db = FakeDB()
    asked = _site_run(monkeypatch, tmp_path, db)
    downloaded, failures = D.process_site(SITE_ROW)
    assert failures == []
    assert downloaded == 1 and asked == [GATE]
    (row,) = db.inserted
    assert (row.original_url, row.filename, row.width, row.height) == (GATE, "hero.webp", 1200, 800)
    assert row.thumb_width is None and row.author == "Jane"
    assert _stored(tmp_path / SITE[:8] / "hero.webp") == ("WEBP", (1200, 800))
    assert db.thumbnails == {SITE: f"/data/images/wiki/{SITE[:8]}/hero.webp"}


@pytest.mark.parametrize("force", [False, True])
def test_a_file_on_disk_that_no_row_names_is_a_named_failure(tmp_path, monkeypatch, force):
    """A run stopped between download and insert: the file is never replaced, never guessed."""
    db = FakeDB()
    asked = _site_run(monkeypatch, tmp_path, db)
    stray = tmp_path / SITE[:8] / "hero.webp"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"left by a run that stopped before its insert")
    downloaded, failures = D.process_site(SITE_ROW, force=force)
    assert downloaded == 0 and asked == [] and db.inserted == []
    (failure,) = failures
    assert (failure.title, failure.url) == (GATE_TITLE, str(stray))
    assert "without a wiki_images row of this site" in failure.reason
    assert stray.read_bytes() == b"left by a run that stopped before its insert"


def test_a_file_on_disk_that_a_row_names_is_done(tmp_path, monkeypatch):
    db = FakeDB([{"site_id": SITE, "original_url": GATE, "filename": "hero.webp"}])
    asked = _site_run(monkeypatch, tmp_path, db)
    (tmp_path / SITE[:8]).mkdir(parents=True)
    (tmp_path / SITE[:8] / "hero.webp").write_bytes(b"registered")
    assert D.process_site(SITE_ROW, force=True) == (1, [])
    assert asked == [] and db.inserted == []


def test_an_insert_that_fails_is_a_named_failure_and_moves_no_thumbnail(tmp_path, monkeypatch):
    db = FakeDB()
    db.fail_insert = OperationalError(
        "INSERT INTO wiki_images", {}, Exception("server closed the connection unexpectedly")
    )
    _site_run(monkeypatch, tmp_path, db)
    downloaded, failures = D.process_site(SITE_ROW)
    assert downloaded == 0
    (failure,) = failures
    assert (failure.title, failure.url) == (GATE_TITLE, GATE)
    assert "its wiki_images row was not written (OperationalError" in failure.reason
    assert db.thumbnails == {}


def test_a_duplicate_row_for_the_original_counts_as_stored(tmp_path, monkeypatch):
    """--force with the file gone: the site already has a row for this original."""
    db = FakeDB([{"site_id": SITE, "original_url": GATE, "filename": "Temple_gate.webp"}])
    _site_run(monkeypatch, tmp_path, db)
    assert D.process_site(SITE_ROW, force=True) == (1, [])
    assert db.inserted == []


def test_an_error_that_is_not_an_image_failure_stops_the_run(monkeypatch):
    """It used to be a warning and `Errors: 1` - and main exited 0."""
    site = {"id": SITE, "name": "Temple of Test", "source_url": None, "source_id": "ancient_nerds"}
    monkeypatch.setattr(D, "get_sites_to_process", lambda source_filter, site_id: [site])

    def broken(site, **kwargs):
        raise KeyError("width")

    monkeypatch.setattr(D, "process_site", broken)
    with pytest.raises(KeyError, match="width"):
        D.run_downloader(site_id=SITE, force=True)

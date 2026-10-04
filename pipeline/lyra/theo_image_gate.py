"""Mechanical image rules a research paper must pass before it ships (defect class G).

The 31-paper audit (docs/reports/theo-paper-defects-2026-10-04.md, section G) measured
what the image gate did not see: `p2_Halley_s_Comet.jpg` shows a hydrothermal vent,
`p14_Manus_Island.jpg` is North Sentinel Island, `cargo-cults` shipped eight image credits
for seven pictures, and the seven image references in
`the-enuma-elish-tiamat-and-the-sitchin-nibiru-controversy` are all dead (504 of the 511
references in the corpus are served, the seven that are not are all in that one paper).
A caption is not evidence of a picture, so the rules here are about the *file*, the
*attribution* and the *reference*, never about whether the prose sounds right.

Out of scope, on purpose: whether a picture shows what its caption says. That needs
somebody who opened the file. What this module can do is refuse to ship a picture nobody
looked at (`unverified`), a picture the site does not serve (`not_served`), a picture
that carries no attribution (`no_credit`, `no_licence`, `no_source_url`, `no_caption`), a
credit with no picture (`credit_picture_mismatch`) and one picture credited twice
(`duplicate_credit`).

Pure functions plus one filesystem existence check. No network, no database, no model
call, nothing read at import time.

`not_served` and the served directory
--------------------------------------
The check resolves every web path under a caller-supplied `served_root`: the directory
nginx and the frontend read as ``/data/``, which is the repo-root ``public/data`` (the
API container sees it at ``/app/public/data``, the VPS host at
``/var/www/ancientnerds/public/data``). A web path
``/data/research-images/<request_id>/<name>`` therefore has to exist as
``<served_root>/research-images/<request_id>/<name>``.

That is deliberately *not* the module-relative directory
`theo_publishing.check_images` uses (`RESEARCH_IMAGES_DIR` =
``<module>/../../public/data/research-images``, checked from wherever the gate runs).
Both spell the same relative path, and on the VPS the compose bind mount
``./public/data:/app/public/data`` makes them one directory, so the difference is not the
path but *which copy of it is inspected, and whether the check runs at all*:

* the images are written by the fetch step into the container path
  (`pipeline/lyra/handlers/probative_images.py` `IMAGES_DIR`), and a failed download
  (`download_candidate`) leaves the `web_path` in the text with no file anywhere - the
  four `writer_img_*` placeholders and three unsaved names of the enuma-elish paper;
* the studio uploads over ssh to the *host* path (`pipeline/studio/remote.py`
  `RESEARCH_IMAGES_ROOT`) and verifies every byte by sha256 afterwards;
* in a workstation checkout `public/data/research-images/` is gitignored and normally
  absent, so a module-relative check run there reads an empty tree and proves nothing
  about the site;
* nothing regenerates or prunes that directory: `static_exporter` manages
  `public/data/{sites,content,library,images}` and never lists `research-images`, so no
  exporter run ever notices a file that is missing from the served set.

Measured over the 31 stored reports, 7 of 511 image references 404 - all seven in one
paper. This module is the layer that names them, one reference at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.lyra.theo_image_captions import clean_gallery_alt

# ---------------------------------------------------------------------------
# The stored shape of a figure
# ---------------------------------------------------------------------------

# Mirror of `_FIGURE_RE` in api/services/theo_blocks.py (and of the frontend's
# galleryParser.ts). Copied, not imported: the import-linter contract "pipeline must
# not import api" (pyproject.toml) is a ratchet, and a figure block is a stored shape,
# not a service.
_FIGURE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>/data/research-images/[^)]+)\)"
    r"(?:\s*\n\n\*(?P<caption>[^*\n][^*]*?)\*"
    r"(?:\s*\n\[Source\]\((?P<url>[^)]+)\))?)?"
)

# A credit line on its own. `image_markdown` writes the caption and the `[Source]` link
# on the lines after the picture; a credit that stands alone is a credit for a file the
# paper does not have.
_CREDIT_LINE_RE = re.compile(r"(?m)^[ \t]*\[Source\]\((?P<url>[^)\n]+)\)[ \t]*$")

# `/data/research-images/<request_id>/<name>`. The name charset forbids `/` and a
# leading dot, so a web path cannot climb out of the served root.
_WEB_PATH_RE = re.compile(
    r"^/data/research-images/(?P<rid>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)

# The QA flag the embed writes into the alt text. theo_image_captions.GALLERY_ALT_RE
# owns the marker format; this reads one field of it.
_ALT_VERIFIED_RE = re.compile(r"^gallery:[^|]*\|verified:(?P<flag>yes|no)\|")

_URL_RE = re.compile(r"^https?://\S+$")

RULE_IDS = (
    "unverified",
    "not_served",
    "not_in_paper_dir",
    "no_credit",
    "no_licence",
    "no_source_url",
    "no_caption",
    "credit_picture_mismatch",
    "duplicate_credit",
)


@dataclass(frozen=True)
class ImageIssue:
    """One rule failure, about one image.

    `rule` is one of RULE_IDS. `image` is the web path or file the issue is about; for
    a report-level rule it is the reference the issue is anchored to. `detail` names what
    is wrong and is reader-facing: the `gallery:` marker is machine data and never
    reaches it.
    """

    rule: str
    detail: str
    image: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _text(value: object) -> str:
    """A stripped string, or '' for anything else (None, a number, a missing key)."""
    return value.strip() if isinstance(value, str) else ""


def _title(alt: str) -> str:
    """The reader-facing title of an alt text: marker stripped, never machine data."""
    return clean_gallery_alt(alt) or "the image"


def _unverified_alt(alt: str) -> bool:
    """True when the alt marker carries the QA flag `verified:no`.

    An alt without the marker, or without a flag field, is not judged here: the flag
    arrived with the gallery embed, and a record that predates it makes no claim about
    its picture either way.
    """
    match = _ALT_VERIFIED_RE.match(alt.strip())
    return match is not None and match.group("flag") == "no"


def parse_figures(report: str) -> list[dict]:
    """Every figure block of a paper report, in reading order.

    One dict per `![alt](src)` block, with the alt text **marker intact** (the caller
    needs `verified:no` out of it), the `src`, the italic caption line and the
    `[Source](url)` line of the same block. `source_url` is '' when the block carries no
    credit, `caption` is '' when it carries none.

    Out of scope: markdown images outside `/data/research-images/` - the hero image's
    own block, a `![](...)` inside a fenced block - are not figures of the paper body.
    """
    return [
        {
            "alt": match.group("alt") or "",
            "src": match.group("src") or "",
            "caption": (match.group("caption") or "").strip(),
            "source_url": (match.group("url") or "").strip(),
        }
        for match in _FIGURE_RE.finditer(report)
    ]


def _credits(report: str) -> list[tuple[int, str]]:
    """Every `[Source]` credit line of the report, as (line start, url)."""
    return [(m.start(), m.group("url").strip()) for m in _CREDIT_LINE_RE.finditer(report)]


def _embeds(report: str) -> list[tuple[int, str]]:
    """Every `![...](...)` picture of the report, as (embed start, src)."""
    return [
        (m.start(), m.group("src") or "")
        for m in _FIGURE_RE.finditer(report)
        if _WEB_PATH_RE.match(m.group("src") or "")
    ]


def _orphan_credit_urls(report: str) -> list[str]:
    """The credit lines no picture owns, in reading order.

    Ownership is positional, not structural. The writer also put images at the end of a
    prose paragraph with their caption and credit on the lines after, a shape
    `_FIGURE_RE` does not attach, so a purely structural match calls three good credits
    of cargo-cults orphans. A credit with no picture between it and the previous credit
    is the defect: it credits a file the paper does not have.
    """
    embeds = _embeds(report)
    orphans: list[str] = []
    previous = -1
    for start, url in _credits(report):
        if not any(previous <= position < start for position, _src in embeds):
            orphans.append(url)
        previous = start
    return orphans


def _uncredited_sources(report: str) -> list[str]:
    """The pictures no credit follows before the next picture starts, in reading order."""
    embeds = _embeds(report)
    credits = [start for start, _url in _credits(report)]
    sources: list[str] = []
    for index, (start, src) in enumerate(embeds):
        end = embeds[index + 1][0] if index + 1 < len(embeds) else float("inf")
        if not any(start <= credit < end for credit in credits):
            sources.append(src)
    return sources


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class _Collector:
    """Issues, with the (rule, image) pairs already reported kept out.

    One defect is one issue: the same file is reachable twice, once through its
    `probative_images` record and once through the figure that embeds it, and a picture
    nobody opened must be named once, not twice.
    """

    def __init__(self) -> None:
        self.issues: list[ImageIssue] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, rule: str, detail: str, image: str) -> None:
        key = (rule, image)
        if key in self._seen:
            return
        self._seen.add(key)
        self.issues.append(ImageIssue(rule=rule, detail=detail, image=image))


def _label(entry: dict, index: int) -> str:
    """What an issue about this record names: its web path, its file, or its position."""
    return _text(entry.get("web_path")) or _text(entry.get("file")) or f"probative_images[{index}]"


def _check_attribution(entry: dict, image: str, out: _Collector) -> None:
    """The four attribution rules of one record.

    CC BY attribution is a licence condition, not a courtesy: 59 % of the corpus is
    Wikimedia/Europeana material.
    """
    if not _text(entry.get("artist")) and not _text(entry.get("source_name")):
        out.add("no_credit", f"{image}: no artist and no source name to attribute it to", image)
    licence = _text(entry.get("license"))
    licence_url = _text(entry.get("license_url"))
    if not licence:
        out.add("no_licence", f"{image}: no licence stated", image)
    elif licence_url and not _URL_RE.match(licence_url):
        out.add("no_licence", f"{image}: licence URL is not a URL: {licence_url}", image)
    if not _text(entry.get("source_url")):
        out.add("no_source_url", f"{image}: no source URL", image)
    if not _text(entry.get("description")):
        out.add("no_caption", f"{image}: no caption (empty description)", image)


def _check_duplicates(entries: list[dict], out: _Collector) -> None:
    """Two records claiming the same source URL, or the same image file, in one paper."""
    by_source: dict[str, str] = {}
    by_file: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        image = _label(entry, index)
        source_url = _text(entry.get("source_url"))
        if source_url:
            first = by_source.setdefault(source_url, image)
            if first != image:
                out.add(
                    "duplicate_credit",
                    f"{image}: same source URL as {first}: {source_url}",
                    image,
                )
        name = _text(entry.get("web_path")).rsplit("/", 1)[-1] or _text(entry.get("file"))
        if name:
            first_file = by_file.setdefault(name, image)
            if first_file != image:
                out.add(
                    "duplicate_credit",
                    f"{image}: same image file as {first_file}",
                    image,
                )


def check_image_entries(entries: list[dict], *, request_id: str) -> list[ImageIssue]:
    """One entry per `probative_images` record (the stored dicts, not the report).

    Per record: the picture was opened (`unverified` - the alt marker says
    `verified:no`, or the record's own `verified` field is false), the web path belongs
    to this paper (`not_in_paper_dir`), the attribution is complete (`no_credit`,
    `no_licence`, `no_source_url`, `no_caption`) and nothing is credited twice
    (`duplicate_credit`).

    A record with no `verified` key is not judged by `unverified`: it predates the flag,
    and `False` is a claim a record makes about itself, not one it omits. Such a record
    is caught by `not_served` when the file is missing, and by the audit that opens the
    picture, not here.

    Out of scope: whether the file is served - that needs a served root, so use
    check_image_report - and whether the picture shows what the caption says.
    """
    out = _Collector()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            out.add(
                "not_in_paper_dir",
                f"probative_images[{index}] is not a record, so it names no file",
                f"probative_images[{index}]",
            )
            continue
        image = _label(entry, index)
        match = _WEB_PATH_RE.match(_text(entry.get("web_path")))
        if match is None:
            out.add(
                "not_in_paper_dir",
                f"{image}: not a /data/research-images/<request_id>/<name> path of this paper",
                image,
            )
        elif match.group("rid") != request_id:
            out.add(
                "not_in_paper_dir",
                f"{image}: lives in research-images/{match.group('rid')}/, "
                f"not in research-images/{request_id}/",
                image,
            )
        if entry.get("verified") is False:
            out.add(
                "unverified",
                f"{image}: nobody has opened this picture; "
                "the caption is not evidence of what it shows",
                image,
            )
        _check_attribution(entry, image, out)
    _check_duplicates(entries, out)
    return out.issues


def _served_file(served_root: Path, web_path: str) -> Path | None:
    """Where a web path must exist on disk, under the directory served as `/data/`.

    None for a path that is not under `/data/research-images/<request_id>/<name>`:
    there is no served location to resolve it to, and the caller reports it as
    `not_in_paper_dir` rather than pretending the file was looked for.
    """
    match = _WEB_PATH_RE.match(web_path)
    if match is None:
        return None
    return served_root / "research-images" / match.group("rid") / match.group("name")


def check_image_report(
    report: str,
    entries: list[dict],
    *,
    request_id: str,
    served_root: str | Path | None,
) -> list[ImageIssue]:
    """Every rule of check_image_entries, plus the ones that need the report or a disk.

    `not_served`: every distinct web path - the `src` of each figure and the `web_path`
    of each record, the hero image included - must exist as a file under `served_root`,
    the directory served as `/data/` (the repo-root `public/data`; the module docstring
    says why the served copy and the module-relative one are not the same thing). This
    is the check the 404 measurements ask for, one reference at a time.

    `served_root=None`, or an empty string, is **not** a pass. A caller that cannot read
    the filesystem gets one `not_served` issue per reference, naming the directory to
    pass, so the gap shows up in the gate output instead of hiding in it. A served root
    that does not exist has the same effect: every reference is reported.

    `unverified` is decided once per image across both sources, so a picture that is
    `verified:no` in its alt *and* false in its record is named once.

    `credit_picture_mismatch`: the number of `[Source]` credit lines in the report
    against the number of pictures, both counts in the detail. cargo-cults shipped 8
    credits for 7 pictures, the eighth one crediting a file the site answers 404 for.
    The reverse - a picture with no credit - is the same rule and names the pictures.

    Out of scope: a `[Source]` line inside a fenced code block, which this module
    cannot tell from a real credit, and a credit URL containing `)`, which
    `_FIGURE_RE` truncates the same way the page renderer does.
    """
    out = _Collector()
    for issue in check_image_entries(entries, request_id=request_id):
        out.add(issue.rule, issue.detail, issue.image)

    figures = parse_figures(report)
    for figure in figures:
        if _unverified_alt(figure["alt"]):
            out.add(
                "unverified",
                f"{figure['src']}: {_title(figure['alt'])} carries verified:no - nobody has "
                "opened this picture, and the caption is not evidence of it",
                figure["src"],
            )

    credits = _credits(report)
    orphans = _orphan_credit_urls(report)
    uncredited = _uncredited_sources(report)
    if len(credits) != len(figures):
        first = orphans[0] if orphans else (uncredited[0] if uncredited else "the report")
        out.add(
            "credit_picture_mismatch",
            f"{len(credits)} image credits for {len(figures)} pictures"
            + (f"; {first} is credited without a picture" if orphans else "")
            + (f"; {len(uncredited)} picture(s) carry no credit" if uncredited else ""),
            first,
        )

    references: list[str] = []
    for web_path in [f["src"] for f in figures] + [
        _text(e.get("web_path")) for e in entries if isinstance(e, dict)
    ]:
        if web_path and web_path not in references:
            references.append(web_path)
    root = Path(served_root) if served_root else None
    for web_path in references:
        served_file = _served_file(root, web_path) if root is not None else None
        if root is not None and served_file is None:
            continue  # not_in_paper_dir already named it; no served location exists
        if served_file is None:
            out.add(
                "not_served",
                f"{web_path}: the served location could not be checked - no served root "
                "given; pass the directory served as /data/ (the repo-root public/data)",
                web_path,
            )
        elif not served_file.is_file():
            out.add(
                "not_served",
                f"{web_path}: no file at the served path {served_file}",
                web_path,
            )
    return out.issues

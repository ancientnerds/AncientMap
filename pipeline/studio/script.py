"""The episode script (spec 4.3) and its validator. Errors block voice, timeline and render.

    {"version": 1, "episode": "<slug>", "fps": 60,
     "voice": {"id": "English_expressive_narrator", "speed": 1.0},
     "captures": [{"id": "platform-01", "kind": "platform", "target": "local",
                   "actions": [{"do": "search", "q": "Baalbek"}]}],
     "beats": [{"id": "b01", "chapter": "Hook", "spoken": "...", "display": "...",
                "hook": true, "factual": true, "role": "twist|verdict|change_mind",
                "evidence": ["e1"],
                "visual": {"block": "PhotoPlate", "props": {...}, "credit": "© Mapbox © Maxar"},
                "cues": [{"at_word": "person", "do": "show", "target": "mk1"}],
                "min_s": 3.0, "lead_s": 0.35, "tail_s": 0.6}],
     "chapters": [{"title": "...", "beat": "b01"}],
     "thumbnails": [{"beat": "b01", "at": 0.6, "text": "Who moved it?"}, ... exactly 3]}

`hook` and `factual` default to false/true, `lead_s`/`tail_s` to LEAD_S/TAIL_S; `credit` (a
non-empty string), `chapter` and `role` are optional. `thumbnails` are the three candidates for
YouTube's A/B test (owner decisions 24, 25): a frame `at` (the share of its beat's scene) and a
teaser `text` of 2-4 words; no candidate may show the answer. Case-file entities enter props only as references: image
and evidence as {"$ref": id}, every ClaimBoard claim as {"$ref": id}, clip/map/page as
{"$capture": id} of a declared capture of the block's kind. A cue is exactly
{at_word, do, target, value?}; `value` only on status (a claim status) and meter ([a, b],
integers 0-100 summing to 100, target "meter"). The local verbs show/hide/highlight/stamp
follow LOCAL_CUES, the mirror of the renderer's cue table (video/src/blocks/index.ts BLOCKS):
which verbs a block takes and which ids of its resolved props they may target. introduce needs
a ClaimBoard of the episode listing the claim; a meter cue needs a Meter beat. Timing rules use
the voice's word timings when words.json exists and an estimate of WORDS_PER_S otherwise;
chapter and clip lengths are checked once the voice exists. A cue's `at_word` names whole
display words (`cue_word_index`, the index timeline.py takes the cue's frame from). Every
string the renderer will draw (the props at the block's registry `drawn` paths, a capture's
credits and its place and pin labels, hook captions, credit lines, chapter titles, thumbnail
teasers) must lie in the brand fonts' glyphs (glyphs.py, the renderer's checkBlocks rule; owner
decision 32: only drawn strings, so an original quote inside a captured page and the page's own
<title> are allowed), each hook word fits one caption line (HOOK_LINE_MAX_CHARS), and only the
last beat may be the ShareCard end card, the one place the link appears in the picture. A
`site_ids` key belongs to a globe distribution take only. Checks that need a
capture not yet recorded are reported as deferred (never skipped) and run after
`episode capture`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pipeline.studio.blocks import FORBIDDEN_BLOCKS, props_errors
from pipeline.studio.casefile import (
    CLAIM_STATUSES,
    CaptureNotRecorded,
    CaseFile,
    CaseFileError,
    Place,
    Quantity,
    refs_in,
    resolve_refs,
    resolved,
)
from pipeline.studio.config import CAPTURE_ID_RE, CAPTURE_KINDS
from pipeline.studio.glyphs import capture_strings, drawn_strings, glyph_problem
from pipeline.studio.spoken import spelling_mismatch
from pipeline.video.shorts_captions import display_text

WORDS_PER_S = 2.6
LEAD_S = 0.35
TAIL_S = 0.6
FPS = 60
HOOK_MAX_S = 32.0
#: The longest hook caption line the renderer draws: stream D's HOOK_LINE_MAX_CHARS in
#: video/src/captions.ts (Task 27 compares the two). HookCaptions sets a line on one row
#: (nowrap, Orbitron 700 at 64 px, 0.06em tracking) in the 1440 px caption zone, where 24
#: uppercase characters fit; captionLines breaks a longer line between words, but one word
#: longer than that cannot be broken.
HOOK_LINE_MAX_CHARS = 24
PLATFORM_RANGE = (3, 5)
PLATFORM_MIN_S = 5.0
PLATFORM_MAX_S = 15.0
CHAPTER_MIN_S = 10.0
CHAPTERS_MIN_FULL = 3
MAP_CREDITS = ("© Mapbox", "© OpenStreetMap")
LOCAL_VERBS = frozenset({"show", "hide", "highlight", "stamp"})
CLAIM_VERBS = frozenset({"introduce", "status"})
CUE_VERBS = LOCAL_VERBS | CLAIM_VERBS | {"meter"}
VALUE_VERBS = frozenset({"status", "meter"})
CUE_KEYS = frozenset({"at_word", "do", "target", "value"})
ROLES = ("twist", "verdict", "change_mind")
FORMATS = ("full", "slice")
#: The capture kind each capture-showing block takes (its props schema's kind enum).
CAPTURE_KIND_OF = {
    "PlatformClip": "platform",
    "GlobeShot": "globe",
    "MapboxFlyover": "globe",
    "MapboxTopdown": "mapbox_topdown",
    "SourceViewer": "source",
}
CLIP_BLOCKS = ("PlatformClip", "GlobeShot", "MapboxFlyover")
#: The globe scenes each globe block shows (stream D's globe.CREDITS split: GlobeShot is our
#: vector globe and carries no map credit, MapboxFlyover a Mapbox take that must).
GLOBE_SCENES_OF = {
    "GlobeShot": ("flyto", "places", "distribution"),
    "MapboxFlyover": ("mapbox_flyin", "mapbox_orbit"),
}
REF_PROPS = {"image": "media", "evidence": "evidence"}
CAPTURE_PROPS = ("clip", "map", "page")
COORD_TOLERANCE = 1e-6
_BEAT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
BEAT_REQUIRED = {"id", "spoken", "display", "evidence", "visual", "cues", "min_s"}
BEAT_OPTIONAL = {"chapter", "hook", "factual", "lead_s", "tail_s", "role"}
#: A world distribution (owner decision 15): at most 12 labelled case-file places, the rest
#: of its up to 500 points are dots by site id (sites.py resolves them at capture time).
DISTRIBUTION_PLACES_MAX = 12
DISTRIBUTION_POINTS_MAX = 500
#: The platform actions whose points the site draws (a measured distance, a proximity circle).
PLATFORM_POINTS = {"measure": ("a", "b"), "proximity": ("at",)}
#: Thumbnail candidates (owner decisions 24, 25): three, each a 2-4 word teaser.
THUMBNAILS = 3
THUMBNAIL_KEYS = frozenset({"beat", "at", "text"})
TEASER_WORDS = (2, 4)
VERDICT_WORDS = frozenset(
    {"SUPPORTED", "REFUTED", "WEAKENED", "CONFIRMED", "DEBUNKED", "PROVEN", "TRUE", "FALSE"}
)

Targets = Callable[[dict[str, Any]], list[str]]


def _ids_of(key: str) -> Targets:
    return lambda props: [item["id"] for item in props[key]]


def _markers(props: dict[str, Any]) -> list[str]:
    return [m["id"] for m in props["image"]["markers"]]


def _pins(props: dict[str, Any]) -> list[str]:
    return [e["target"] for e in props["map"]["events"] if e["name"] == "pin" and "target" in e]


def _globe_places(props: dict[str, Any]) -> list[str]:
    return [
        e["target"]
        for e in props["clip"]["events"]
        if e["name"] == "place" and {"target", "x", "y", "label"} <= set(e)
    ]


def _evidence_id(props: dict[str, Any]) -> list[str]:
    return [props["evidence"]["id"]]


def _zoom_ends(props: dict[str, Any]) -> list[str]:
    return [props["small"]["id"], props["large"]["id"]]


#: The renderer's local cue table (video/src/blocks/index.ts BLOCKS, the single definition),
#: evaluated on a beat's resolved props: block -> verb -> the ids that verb may target.
LOCAL_CUES: dict[str, dict[str, Targets]] = {
    "PhotoPlate": dict.fromkeys(("show", "hide", "highlight"), _markers),
    "MapboxTopdown": dict.fromkeys(("show", "highlight"), _pins),
    "PlatformClip": {},
    "GlobeShot": {"show": _globe_places},
    "MapboxFlyover": {},
    "SourceViewer": {"highlight": _evidence_id},
    "EvidenceCard": dict.fromkeys(("highlight", "stamp"), _evidence_id),
    "QuoteCard": {"highlight": _evidence_id},
    "ClaimBoard": {"highlight": _ids_of("claims")},
    "Meter": {},
    "ScaleDrawing": {"show": _ids_of("objects")},
    "UnitGrid": {"show": _ids_of("groups")},
    "BarChart": {"show": _ids_of("bars")},
    "Timeline": {"show": _ids_of("events")},
    "Diagram": {"show": _ids_of("elements")},
    "ListCard": {"show": _ids_of("items")},
    "ShareCard": {},
    "ScaleZoom": {"show": _zoom_ends},
}


@dataclass
class ScriptReport:
    errors: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def speech_seconds(beat: dict[str, Any], words: dict[str, Any] | None) -> float:
    if words is not None and beat["id"] in words:
        return float(words[beat["id"]]["duration_s"])
    return len(beat["spoken"].split()) / WORDS_PER_S


def scene_seconds(beat: dict[str, Any], speech_s: float) -> float:
    """max(min_s, lead + speech + tail): how long a beat's scene stays on screen."""
    lead = float(beat.get("lead_s", LEAD_S))
    tail = float(beat.get("tail_s", TAIL_S))
    return max(float(beat["min_s"]), lead + speech_s + tail)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"$ref"} and isinstance(value["$ref"], str)


def _top_level(script: Any, slug: str, report: ScriptReport) -> bool:
    if not isinstance(script, dict):
        report.errors.append("script.json must be an object")
        return False
    required = {"version", "episode", "fps", "voice", "beats", "chapters", "thumbnails"}
    missing = sorted(required - set(script))
    unknown = sorted(set(script) - required - {"captures"})
    if missing or unknown:
        report.errors.append(f"script keys: missing {missing}, unknown {unknown}")
        return False
    if script["version"] != 1:
        report.errors.append("version must be 1")
    if script["episode"] != slug:
        report.errors.append(f"episode {script['episode']!r} is not this episode ({slug!r})")
    if script["fps"] != FPS:
        report.errors.append("fps must be 60")
    voice = script["voice"]
    if not isinstance(voice, dict) or set(voice) != {"id", "speed"}:
        report.errors.append("voice must be {id, speed}")
    elif not isinstance(voice["speed"], (int, float)) or not 0.5 <= voice["speed"] <= 2.0:
        report.errors.append("voice.speed must be between 0.5 and 2.0")
    if not isinstance(script["beats"], list) or not script["beats"]:
        report.errors.append("beats must be a non-empty list")
        return False
    return True


def _captures(script: dict[str, Any], report: ScriptReport) -> dict[str, dict[str, Any]]:
    """The declared capture specs by id."""
    specs: dict[str, dict[str, Any]] = {}
    ids: list[str] = []
    for n, cap in enumerate(script.get("captures", []), start=1):
        if not isinstance(cap, dict) or not isinstance(cap.get("id"), str):
            report.errors.append(f"capture {n}: needs a string id")
            continue
        if not CAPTURE_ID_RE.fullmatch(cap["id"]):
            report.errors.append(f"capture {cap['id']!r}: id must match {CAPTURE_ID_RE.pattern}")
        if cap.get("kind") not in CAPTURE_KINDS:
            report.errors.append(f"capture {cap['id']}: kind must be one of {list(CAPTURE_KINDS)}")
        ids.append(cap["id"])
        specs[cap["id"]] = cap
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        report.errors.append(f"duplicate capture ids {dupes}")
    return specs


def _same_place(cf: CaseFile, cid: str, point: Any, report: ScriptReport) -> None:
    """A place a capture spec shows must be a case-file place at the case file's coordinates,
    and the label the video draws for it, when it has one, the case file's name."""
    places = {p.id: p for p in cf.places}
    pid = point.get("id") if isinstance(point, dict) else None
    place = places.get(pid) if isinstance(pid, str) else None
    if place is None:
        report.errors.append(f"capture {cid}: place {pid} is not in the case file")
        return
    lat, lng = point.get("lat"), point.get("lng")
    if not (
        _number(lat)
        and _number(lng)
        and abs(lat - place.lat) <= COORD_TOLERANCE
        and abs(lng - place.lng) <= COORD_TOLERANCE
    ):
        report.errors.append(f"capture {cid}: place {pid} lat/lng differ from the case file")
    if "label" in point and point["label"] != place.name:
        report.errors.append(
            f"capture {cid}: place {pid} label {point['label']!r} is not the case file's name "
            f"{place.name!r}"
        )


def place_at(cf: CaseFile, point: Any) -> Place | None:
    """The case-file place whose coordinates `point` ({lat, lng}) lies on, or None."""
    lat, lng = (point.get("lat"), point.get("lng")) if isinstance(point, dict) else (None, None)
    if not (_number(lat) and _number(lng)):
        return None
    return next(
        (
            p
            for p in cf.places
            if abs(lat - p.lat) <= COORD_TOLERANCE and abs(lng - p.lng) <= COORD_TOLERANCE
        ),
        None,
    )


def _at_a_place(cf: CaseFile, point: Any) -> bool:
    """`point` ({lat, lng}) lies on a case-file place's coordinates."""
    return place_at(cf, point) is not None


def _mapbox_take(cf: CaseFile, cid: str, spec: dict[str, Any], report: ScriptReport) -> None:
    """A Mapbox fly-in or orbit centres on a case-file place. Its optional `country` is drawn
    (the recorder highlights that country's outline), so it is shown data too: the place must
    carry a site_id, and episode.country_problems checks `country` against that site's `c` in
    the repo-root site export (Task 18)."""
    place = place_at(cf, spec)
    if place is None:
        report.errors.append(f"capture {cid}: lat/lng are not the coordinates of a case-file place")
        return
    if "country" not in spec:
        return
    if not (isinstance(spec["country"], str) and spec["country"].strip()):
        report.errors.append(f"capture {cid}: country must be a non-empty string")
    elif place.site_id is None:
        report.errors.append(
            f"capture {cid}: country needs case-file place {place.id} to carry a site_id "
            "(the country is the site export's country of that site)"
        )


def _listed(cid: str, spec: dict[str, Any], key: str, report: ScriptReport) -> list[Any]:
    """spec[key] as a list ([] when absent); anything else is reported."""
    value = spec.get(key, [])
    if not isinstance(value, list):
        report.errors.append(f"capture {cid}: {key} must be a list")
        return []
    return value


def _distribution(cf: CaseFile, cid: str, spec: dict[str, Any], report: ScriptReport) -> None:
    """A world distribution (owner decision 15): `places` are its named pins, labelled
    case-file places (at most 12); `site_ids` are its dots, unified_sites ids that
    `episode capture` resolves from the repo-root site export (sites.py), never case-file
    places. 1 to 500 points in total."""
    places = _listed(cid, spec, "places", report)
    for point in places:
        _same_place(cf, cid, point, report)
        label = point.get("label") if isinstance(point, dict) else None
        if isinstance(point, dict) and not (isinstance(label, str) and label.strip()):
            report.errors.append(
                f"capture {cid}: place {point.get('id')} needs its label (a distribution's "
                "places are its named pins; further sites go in site_ids)"
            )
    if len(places) > DISTRIBUTION_PLACES_MAX:
        report.errors.append(
            f"capture {cid}: a distribution names at most {DISTRIBUTION_PLACES_MAX} places; "
            "further sites go in site_ids"
        )
    site_ids = spec.get("site_ids", [])
    if (
        not isinstance(site_ids, list)
        or not all(isinstance(s, str) and s.strip() for s in site_ids)
        or len(set(site_ids)) != len(site_ids)
    ):
        report.errors.append(f"capture {cid}: site_ids must be a list of unique site ids")
        return
    total = len(places) + len(site_ids)
    if not 1 <= total <= DISTRIBUTION_POINTS_MAX:
        report.errors.append(
            f"capture {cid}: a distribution shows 1 to {DISTRIBUTION_POINTS_MAX} points "
            f"(places plus site_ids), got {total}"
        )


def _capture_bindings(specs: dict[str, dict[str, Any]], cf: CaseFile, report: ScriptReport) -> None:
    """Capture specs show only verified case-file data: places (flyto, places, a
    distribution's named pins, top-down pins) at the case file's coordinates under the case
    file's names, a Mapbox fly-in or orbit centred on a case-file place (its optional
    `country` bound to that place's site, `_mapbox_take`), platform measure and
    proximity points on case-file places, verified quotes, verified paper anchors. A flyto
    without `place` (a regional view) names no place and stays unbound; a distribution's dots
    are site ids (owner decision 15), and no other take carries `site_ids` (sites.py would
    resolve them into places the other scenes refuse only at capture)."""
    verified = [e for e in cf.evidence if e.verification.status == "verified"]
    for cid, spec in specs.items():
        kind = spec.get("kind")
        if "site_ids" in spec and not (kind == "globe" and spec.get("scene") == "distribution"):
            report.errors.append(
                f"capture {cid}: site_ids belong only to a globe distribution take "
                "(owner decision 15)"
            )
        if kind == "globe" and spec.get("scene") == "flyto" and "place" in spec:
            place = spec["place"]
            if isinstance(place, dict):
                point = {**place, "lat": spec.get("lat"), "lng": spec.get("lng")}
                _same_place(cf, cid, point, report)
            else:
                report.errors.append(f"capture {cid}: place must be {{id, label}}")
        elif kind == "globe" and spec.get("scene") == "places":
            for point in _listed(cid, spec, "places", report):
                _same_place(cf, cid, point, report)
        elif kind == "globe" and spec.get("scene") == "distribution":
            _distribution(cf, cid, spec, report)
        elif kind == "globe" and spec.get("scene") in GLOBE_SCENES_OF["MapboxFlyover"]:
            _mapbox_take(cf, cid, spec, report)
        elif kind == "mapbox_topdown":
            for point in _listed(cid, spec, "pins", report):
                _same_place(cf, cid, point, report)
        elif kind == "platform":
            for i, action in enumerate(_listed(cid, spec, "actions", report)):
                verb = action.get("do") if isinstance(action, dict) else None
                for key in PLATFORM_POINTS.get(verb, ()):
                    if not _at_a_place(cf, action.get(key)):
                        report.errors.append(
                            f"capture {cid}: actions[{i}].{key} is not the coordinates of a "
                            "case-file place"
                        )
        elif kind == "source" and "url" in spec:
            url = spec["url"]
            if not any(
                e.source.url == url and e.source.quote == spec.get("quote") for e in verified
            ):
                report.errors.append(
                    f"capture {cid}: quote is not the verified quote of a case-file evidence "
                    f"item from {url}"
                )
        elif kind == "source" and "paper" in spec:
            anchor = spec.get("anchor")
            if not any(e.paper_anchor == anchor for e in verified):
                report.errors.append(
                    f"capture {cid}: anchor {anchor} is not the paper_anchor of a verified "
                    "evidence item"
                )
            if cf.paper is not None and spec["paper"] != cf.paper.slug:
                report.errors.append(
                    f"capture {cid}: paper {spec['paper']} is not the case file's paper "
                    f"({cf.paper.slug})"
                )


def _capture_ids_in(value: Any) -> list[str]:
    if isinstance(value, dict):
        if set(value) == {"$capture"}:
            return [value["$capture"]]
        return [c for v in value.values() for c in _capture_ids_in(v)]
    if isinstance(value, list):
        return [c for v in value for c in _capture_ids_in(v)]
    return []


def _dicts_with_id(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        own = [value] if isinstance(value.get("id"), str) else []
        return own + [d for v in value.values() for d in _dicts_with_id(v)]
    if isinstance(value, list):
        return [d for v in value for d in _dicts_with_id(v)]
    return []


def _beat_field_problems(beat: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("spoken", "display"):
        if not isinstance(beat[key], str) or not beat[key].strip():
            problems.append(f"{key} must be a non-empty string")
    if not isinstance(beat["evidence"], list) or not all(
        isinstance(e, str) for e in beat["evidence"]
    ):
        problems.append("evidence must be a list of evidence ids")
    if not isinstance(beat["cues"], list):
        problems.append("cues must be a list")
    if not _number(beat["min_s"]) or beat["min_s"] <= 0:
        problems.append("min_s must be a number > 0")
    for key in ("lead_s", "tail_s"):
        if key in beat and (not _number(beat[key]) or beat[key] < 0):
            problems.append(f"{key} must be a number >= 0")
    for key in ("hook", "factual"):
        if key in beat and not isinstance(beat[key], bool):
            problems.append(f"{key} must be true or false")
    if "role" in beat and beat["role"] not in ROLES:
        problems.append(f"role must be one of {list(ROLES)}")
    return problems


def _reference_problems(
    block: str, props: dict[str, Any], kinds: dict[str, str], specs: dict[str, dict[str, Any]]
) -> list[str]:
    """Case-file data enters props only as a reference, so every case-file rule applies."""
    problems: list[str] = []
    for key, kind in REF_PROPS.items():
        if key in props:
            value = props[key]
            if not _is_ref(value) or kinds.get(value["$ref"], kind) != kind:
                problems.append(
                    f'props.{key} must reference the case file ({{"$ref": <{kind} id>}})'
                )
    if block == "ClaimBoard" and "claims" in props:
        claims = props["claims"]
        if not isinstance(claims, list) or not all(
            _is_ref(c) and kinds.get(c["$ref"], "claim") == "claim" for c in claims
        ):
            problems.append('props.claims must reference the case file ([{"$ref": <claim id>}])')
    for key in CAPTURE_PROPS:
        if key not in props:
            continue
        value = props[key]
        if not (isinstance(value, dict) and set(value) == {"$capture"}):
            problems.append(f'props.{key} must reference a capture ({{"$capture": <capture id>}})')
            continue
        cid = value["$capture"]
        want = CAPTURE_KIND_OF.get(block)
        if want is not None and cid in specs and specs[cid].get("kind") != want:
            problems.append(
                f"props.{key}: {block} needs a {want} capture, {cid!r} is {specs[cid].get('kind')}"
            )
        elif (
            block in GLOBE_SCENES_OF
            and cid in specs
            and specs[cid].get("scene") not in GLOBE_SCENES_OF[block]
        ):
            problems.append(
                f"props.{key}: {block} needs a globe take of scene "
                f"{list(GLOBE_SCENES_OF[block])}, {cid!r} is {specs[cid].get('scene')!r}"
            )
    return problems


def _quantity_elements(block: str, raw: dict[str, Any]) -> list[Any]:
    """The props elements that may show a case-file quantity: BarChart bars, ScaleZoom ends."""
    if block == "BarChart" and isinstance(raw.get("bars"), list):
        return raw["bars"]
    if block == "ScaleZoom":
        return [raw[end] for end in ("small", "large") if isinstance(raw.get(end), dict)]
    return []


def _quantity_problems(
    block: str, raw: dict[str, Any], quantities: dict[str, Quantity]
) -> list[str]:
    """Only a BarChart bar or a ScaleZoom end shows a quantity: its value and the block's unit
    are the case file's (a range [low, high] only a BarChart draws: linear bars, owner decision
    31). No other props element may use a quantity id."""
    shown = _quantity_elements(block, raw)
    problems: list[str] = []
    for element in _dicts_with_id(raw):
        quantity = quantities.get(element["id"])
        if quantity is None:
            continue
        if not any(element is e for e in shown):
            problems.append(
                f"element {element['id']} uses a quantity id; only a BarChart bar or a "
                "ScaleZoom end shows a quantity"
            )
            continue
        if block == "ScaleZoom" and isinstance(quantity.value, list):
            problems.append(
                f"element {element['id']}: a range quantity is shown as a range in a BarChart, "
                "not in a ScaleZoom"
            )
            continue
        if element.get("value") != quantity.value:
            problems.append(
                f"element {element['id']} must show quantity {quantity.id} as {quantity.value}"
            )
        if raw.get("unit") != quantity.unit:
            problems.append(
                f"element {element['id']} shows quantity {quantity.id} in {raw.get('unit')}; "
                f"the case file says {quantity.unit}"
            )
    return problems


def _glyph_problems(
    bid: str,
    beat: dict[str, Any],
    drawn: list[str],
    props: dict[str, Any] | None,
    entities: dict[str, dict[str, Any]],
    kinds: dict[str, str],
    captures: dict[str, dict[str, Any]] | None,
) -> list[str]:
    """Every string of the beat the renderer draws, in the brand fonts (its checkBlocks rule;
    owner decision 32: drawn strings only): the props at the block's registry `drawn` paths
    (once they resolve), the drawn strings of every capture it shows (glyphs.capture_strings:
    credits, place and pin labels), the hook captions (display tokens uppercased, as
    timeline.py emits them) and the scene's credit lines (visual.credit,
    `Photo: <attribution> (<license>)` of every referenced media item). Ids, paths, URLs, a
    captured page's own <title> and a SourceViewer's quote (pixels of the captured page) are
    not drawn as text."""
    visual = beat["visual"]
    texts: list[tuple[str, str]] = drawn_strings(props, drawn, "props") if props is not None else []
    if beat.get("hook", False):
        texts.extend(
            (f"display token {n}", token.upper())
            for n, token in enumerate(beat["display"].split(), start=1)
            if display_text(token)
        )
    if "credit" in visual:
        texts.append(("visual.credit", visual["credit"]))
    for cid in _capture_ids_in(visual["props"]):
        if captures is not None and cid in captures:
            texts.extend(capture_strings(captures[cid], f"capture {cid}"))
    for ref in refs_in(visual["props"]):
        if kinds.get(ref) == "media":
            m = entities[ref]
            texts.append((f"credit of media {ref}", f"Photo: {m['attribution']} ({m['license']})"))
    return [p for at, text in texts if (p := glyph_problem(f"{bid}: {at}", text)) is not None]


def _hook_word_problems(display: str) -> list[str]:
    """A hook caption word is the display token uppercased with its punctuation (timeline.py);
    the renderer breaks caption lines between words at HOOK_LINE_MAX_CHARS, so the one line it
    cannot break is a single longer word. Refused before the voice: the fix is a new display
    (and spoken) word, which a narration made afterwards would have to follow."""
    return [
        f"hook word {token!r} is longer than {HOOK_LINE_MAX_CHARS} characters and cannot fit "
        "a caption line"
        for token in display.split()
        if display_text(token) and len(token.upper()) > HOOK_LINE_MAX_CHARS
    ]


def cue_word_index(display: str, at_word: str) -> int | None:
    """The index of the display token a cue's `at_word` names, or None.

    The words of `at_word` must match a run of whole display tokens, each compared as
    `shorts_captions.display_text(token).lower()` (edge punctuation dropped); the first such
    run wins. A match inside a longer token never counts: "one" is not the "one" in "stone".
    timeline.py takes the cue's frame from the word timing at this index.
    """
    keys = [display_text(token).lower() for token in display.split()]
    wanted = [display_text(word).lower() for word in at_word.split()]
    if not wanted:
        return None
    for i in range(len(keys) - len(wanted) + 1):
        if keys[i : i + len(wanted)] == wanted:
            return i
    return None


def _cue_problems(cue: Any, display: str, claim_ids: set[str]) -> list[str]:
    """The cue's own shape: keys, verb, word, target and value."""
    if not isinstance(cue, dict):
        return ["a cue is an object {at_word, do, target, value?}"]
    unknown = sorted(set(cue) - CUE_KEYS)
    if unknown:
        return [f"unknown cue keys {unknown}"]
    verb = cue.get("do")
    if verb not in CUE_VERBS:
        return [f"do must be one of {sorted(CUE_VERBS)}"]
    problems: list[str] = []
    at_word, target = cue.get("at_word"), cue.get("target")
    if not isinstance(at_word, str) or not at_word.strip():
        problems.append("at_word must be a non-empty string")
    elif cue_word_index(display, at_word) is None:
        problems.append(f"at_word {at_word!r} is not in display")
    if not isinstance(target, str) or not target.strip():
        problems.append("target must be a non-empty string")
    if ("value" in cue) != (verb in VALUE_VERBS):
        problems.append(
            f"a {verb} cue takes no value" if "value" in cue else f"a {verb} cue needs a value"
        )
        return problems
    value = cue.get("value")
    if verb in CLAIM_VERBS and target not in claim_ids:
        problems.append(f"{verb} targets a claim id, got {target!r}")
    if verb == "status" and value not in CLAIM_STATUSES:
        problems.append(f"status value must be one of {list(CLAIM_STATUSES)}")
    if verb == "meter" and (
        target != "meter"
        or not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100 for v in value)
        or sum(value) != 100
    ):
        problems.append(
            "meter cue targets 'meter' with value [a, b], integers 0-100 summing to 100"
        )
    return problems


def validate_script(
    script: Any,
    cf: CaseFile,
    registry: dict[str, dict[str, Any]],
    *,
    slug: str,
    fmt: str,
    words: dict[str, Any] | None = None,
    captures: dict[str, dict[str, Any]] | None = None,
) -> ScriptReport:
    report = ScriptReport()
    if fmt not in FORMATS:
        report.errors.append(f"episode format must be one of {list(FORMATS)}")
    if not _top_level(script, slug, report):
        return report
    specs = _captures(script, report)
    _capture_bindings(specs, cf, report)
    entities = resolved(cf)
    kinds = {
        **{c.id: "claim" for c in cf.claims},
        **{e.id: "evidence" for e in cf.evidence},
        **{p.id: "place" for p in cf.places},
        **{q.id: "quantity" for q in cf.quantities},
        **{m.id: "media" for m in cf.media},
    }
    evidence = {e.id: e for e in cf.evidence}
    quantities = {q.id: q for q in cf.quantities}
    claim_status = {c.id: c.status for c in cf.claims}
    claim_ids = set(claim_status)
    beats: list[dict[str, Any]] = script["beats"]
    ids = [b.get("id") for b in beats if isinstance(b, dict)]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        report.errors.append(f"duplicate beat ids {dupes}")

    hook_s = 0.0
    hook_beats = 0
    hook_done = False
    platform: list[tuple[str, float]] = []
    blocks_used: list[str] = []
    roles: dict[str, int] = {}
    board_at: dict[str, int] = {}
    intro_at: dict[str, int] = {}
    evidence_at: dict[str, list[int]] = {}
    status_at: dict[str, list[int]] = {}
    introduces: list[tuple[str, str]] = []
    meter_cued = False
    verdict_at: int | None = None
    malformed = False
    for idx, beat in enumerate(beats):
        if not isinstance(beat, dict):
            report.errors.append(f"beat {idx + 1}: not an object")
            continue
        missing = sorted(BEAT_REQUIRED - set(beat))
        unknown = sorted(set(beat) - BEAT_REQUIRED - BEAT_OPTIONAL)
        bid = str(beat.get("id", f"#{idx + 1}"))
        if missing or unknown:
            report.errors.append(f"{bid}: missing {missing}, unknown {unknown}")
            malformed = True
            continue
        if not _BEAT_ID_RE.fullmatch(bid):
            report.errors.append(f"{bid}: id must be lowercase letters, digits, hyphens")
        fields = _beat_field_problems(beat)
        if fields:
            report.errors.extend(f"{bid}: {p}" for p in fields)
            malformed = True
            continue
        speech = speech_seconds(beat, words)
        seconds = scene_seconds(beat, speech)
        # hook: a leading run of beats, at most HOOK_MAX_S of screen time
        if beat.get("hook", False):
            if hook_done:
                report.errors.append(f"{bid}: hook beats must all come first")
            hook_s += seconds
            hook_beats += 1
            report.errors.extend(f"{bid}: {p}" for p in _hook_word_problems(beat["display"]))
        else:
            hook_done = True
        if "role" in beat:
            roles.setdefault(beat["role"], idx)
        # evidence
        if beat.get("factual", True) and not beat["evidence"]:
            report.errors.append(f"{bid}: a factual beat lists its evidence ids")
        for eid in beat["evidence"]:
            item = evidence.get(eid)
            if item is None:
                report.errors.append(f"{bid}: evidence {eid} is not in the case file")
            elif item.verification.status != "verified":
                report.errors.append(
                    f"{bid}: evidence {eid} is {item.verification.status}, not verified"
                )
            else:
                evidence_at.setdefault(item.claim_id, []).append(idx)
        # spoken vs display
        mismatch = spelling_mismatch(beat["spoken"], beat["display"])
        if mismatch:
            report.errors.append(
                f"{bid}: display differs from spoken beyond number spelling ({mismatch})"
            )
        # visual
        visual = beat["visual"]
        if (
            not isinstance(visual, dict)
            or not {"block", "props"} <= set(visual)
            or not set(visual) <= {"block", "props", "credit"}
            or not isinstance(visual["props"], dict)
        ):
            report.errors.append(f"{bid}: visual must be {{block, props (object), credit?}}")
            continue
        if "credit" in visual and (
            not isinstance(visual["credit"], str) or not visual["credit"].strip()
        ):
            report.errors.append(f"{bid}: visual.credit must be a non-empty string")
            continue
        block = visual["block"]
        if block in FORBIDDEN_BLOCKS:
            report.errors.append(
                f"{bid}: block {block} (title card / on-screen agent) is not allowed"
            )
            continue
        entry = registry.get(block)
        if entry is None:
            report.errors.append(f"{bid}: block {block} is not in the renderer's registry")
            continue
        blocks_used.append(block)
        if block == "ShareCard" and idx != len(beats) - 1:
            # the end card is the one place the link appears in the picture (platform
            # moments are never an advert): full episodes and slices alike
            report.errors.append(f"{bid}: ShareCard is the end card; only the last beat may use it")
        raw = visual["props"]
        report.errors.extend(f"{bid}: {p}" for p in _reference_problems(block, raw, kinds, specs))
        for ref in refs_in(raw):
            item = evidence.get(ref)
            if item is not None and item.verification.status != "verified":
                report.errors.append(f"{bid}: props show evidence {ref}, which is not verified")
        for cid in _capture_ids_in(raw):
            if cid not in specs:
                report.errors.append(f"{bid}: $capture {cid!r} is not declared in captures")
        report.errors.extend(f"{bid}: {p}" for p in _quantity_problems(block, raw, quantities))
        if block == "ClaimBoard" and isinstance(raw.get("claims"), list):
            for claim in raw["claims"]:
                if _is_ref(claim) and claim["$ref"] in claim_ids:
                    board_at.setdefault(claim["$ref"], idx)
        if block == "Meter" and (
            raw.get("hypotheses") != cf.meter.hypotheses or raw.get("start") != cf.meter.start
        ):
            report.errors.append(f"{bid}: Meter hypotheses/start must equal the case file's meter")
        if block == "SourceViewer":
            _source_viewer(bid, raw, specs, cf, report)
        props: dict[str, Any] | None = None
        deferred = False
        try:
            candidate = resolve_refs(raw, entities, captures)
        except CaptureNotRecorded as exc:
            report.deferred.append(f"{bid}: props not checked yet ({exc})")
            deferred = True
        except CaseFileError as exc:
            report.errors.append(f"{bid}: {exc}")
        else:
            schema = props_errors(entry["props"], candidate)
            report.errors.extend(f"{bid}: {p}" for p in schema)
            props = None if schema else candidate
        if entry["map"]:
            _map_credit(bid, visual, captures, report)
        if entry["platform"]:
            platform.append((bid, seconds))
        if props is not None and block in CLIP_BLOCKS and words is not None:
            _clip_length(bid, props, seconds, report)
        report.errors.extend(
            _glyph_problems(bid, beat, entry["drawn"], props, entities, kinds, captures)
        )
        # cues
        for n, cue in enumerate(beat["cues"], start=1):
            where = f"{bid} cue {n}"
            problems = _cue_problems(cue, beat["display"], claim_ids)
            if problems:
                report.errors.extend(f"{where}: {p}" for p in problems)
                continue
            verb, target = cue["do"], cue["target"]
            if verdict_at is None and (
                verb == "meter" or (verb == "status" and cue["value"] != "pending")
            ):
                verdict_at = idx
            if verb == "introduce":
                intro_at.setdefault(target, idx)
                introduces.append((where, target))
            elif verb == "status":
                status_at.setdefault(target, []).append(idx)
            elif verb == "meter":
                meter_cued = True
            elif deferred:
                report.deferred.append(f"{where}: {verb} {target} checked with the props")
            elif props is not None:
                table = LOCAL_CUES.get(block, {})
                if verb not in table:
                    report.errors.append(f"{where}: the block does not take {verb} cues")
                elif target not in (targets := table[verb](props)):
                    shown = ", ".join(targets) or "none"
                    report.errors.append(
                        f"{where}: {verb} {target}: not a target of this block ({shown})"
                    )

    if hook_s > HOOK_MAX_S:
        how = "measured" if words is not None else "estimated"
        report.errors.append(
            f"hook is {hook_s:.1f} s of screen time ({how}); max {HOOK_MAX_S:.0f} s"
        )
    if fmt == "full" and not PLATFORM_RANGE[0] <= len(platform) <= PLATFORM_RANGE[1]:
        report.errors.append(
            f"{len(platform)} platform moments; a full episode has {PLATFORM_RANGE[0]}-{PLATFORM_RANGE[1]}"
        )
    for bid, seconds in platform:
        if seconds < PLATFORM_MIN_S:
            report.errors.append(
                f"{bid}: platform moment of {seconds:.1f} s (min {PLATFORM_MIN_S:.0f} s)"
            )
        if seconds > PLATFORM_MAX_S:
            report.errors.append(
                f"{bid}: platform moment of {seconds:.1f} s (max {PLATFORM_MAX_S:.0f} s)"
            )
    for where, target in introduces:
        if target not in board_at:
            report.errors.append(
                f"{where}: introduce {target}: no ClaimBoard of the episode lists this claim"
            )
    if meter_cued and "Meter" not in blocks_used:
        report.errors.append("a meter cue needs a Meter beat")
    for claim in board_at:
        if claim_status[claim] != "pending":
            report.errors.append(
                f"claim {claim}: a claim on the board starts 'pending' in the case file "
                f"(verdicts come from status cues), got {claim_status[claim]!r}"
            )
        at = intro_at.get(claim)
        if at is None:
            report.errors.append(f"claim {claim}: on the board but never introduced")
            continue
        after = [i for i in evidence_at.get(claim, []) if i >= at]
        if not after:
            report.errors.append(f"claim {claim}: introduced but no evidence beat follows")
            continue
        if not [i for i in status_at.get(claim, []) if i >= after[0]]:
            report.errors.append(f"claim {claim}: no status beat after its evidence")
    if fmt == "full":
        _spine(beats, blocks_used, hook_beats, roles, report)
    if words is None and any(b in CLIP_BLOCKS for b in blocks_used):
        report.deferred.append("clip lengths are checked after the voice step")
    _chapters(script, beats, None if malformed else words, fmt, report)
    _thumbnails(script["thumbnails"], beats, verdict_at, report)
    return report


def _thumbnails(
    items: Any, beats: list[dict[str, Any]], verdict_at: int | None, report: ScriptReport
) -> None:
    """Three thumbnail candidates for YouTube's A/B test (owner decisions 24, 25), none of them
    showing the answer: not in a twist, verdict or change-mind beat, not in a beat after the
    one with the first verdict cue (a claim status other than pending, or a meter move; inside
    that beat `episode timeline` refuses a frame at or after the cue), and a teaser of 2-4
    words (a question or riddle) that names no verdict and uses only the brand glyphs."""
    if not isinstance(items, list) or len(items) != THUMBNAILS:
        report.errors.append(f"thumbnails must be a list of exactly {THUMBNAILS} candidates")
        return
    index = {b["id"]: i for i, b in enumerate(beats) if isinstance(b, dict) and "id" in b}
    seen: list[Any] = []
    for i, item in enumerate(items):
        where = f"thumbnails[{i}]"
        if not isinstance(item, dict) or set(item) != THUMBNAIL_KEYS:
            report.errors.append(f"{where} must be exactly {{beat, at, text}}")
            seen.append(None)
            continue
        beat, at, text = item["beat"], item["at"], item["text"]
        if beat not in index:
            report.errors.append(f"{where}: beat {beat!r} is not a beat of the script")
        elif beats[index[beat]].get("role") in ROLES:
            role = beats[index[beat]]["role"]
            report.errors.append(
                f"{where}: beat {beat} is the {role} beat: a thumbnail never shows the answer"
            )
        elif verdict_at is not None and index[beat] > verdict_at:
            report.errors.append(
                f"{where}: beat {beat} comes after the first verdict cue (beat "
                f"{beats[verdict_at]['id']}): a thumbnail never shows the answer"
            )
        if not _number(at) or not 0 <= at < 1:
            report.errors.append(f"{where}: at is the share of the beat's scene, 0 <= at < 1")
        if not isinstance(text, str):
            report.errors.append(f"{where}: text must be a string")
            seen.append(None)
            continue
        words = len(text.split())
        if not TEASER_WORDS[0] <= words <= TEASER_WORDS[1]:
            report.errors.append(
                f"{where}: the teaser has {words} words; it has {TEASER_WORDS[0]}-{TEASER_WORDS[1]}"
            )
        named = sorted(VERDICT_WORDS & set(re.findall(r"[A-Z]+", text.upper())))
        if named:
            report.errors.append(
                f"{where}: the teaser names the answer ({', '.join(named)}): never show it"
            )
        problem = glyph_problem(f"{where}.text", text)
        if problem is not None:
            report.errors.append(problem)
        if item in seen:
            report.errors.append(f"{where}: the same candidate as thumbnails[{seen.index(item)}]")
        seen.append(item)


def _source_viewer(
    bid: str,
    raw: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    cf: CaseFile,
    report: ScriptReport,
) -> None:
    """The captured page must be the evidence's own source quote or its paper paragraph."""
    page, shown = raw.get("page"), raw.get("evidence")
    if not (isinstance(page, dict) and page.get("$capture") in specs and _is_ref(shown)):
        return
    cid, eid = page["$capture"], shown["$ref"]
    item = next((e for e in cf.evidence if e.id == eid), None)
    if item is None:
        return
    spec = specs[cid]
    same_quote = spec.get("url") == item.source.url and spec.get("quote") == item.source.quote
    same_anchor = (
        cf.paper is not None
        and spec.get("paper") == cf.paper.slug
        and spec.get("anchor") == item.paper_anchor
    )
    if not (same_quote or same_anchor):
        report.errors.append(
            f"{bid}: SourceViewer page {cid} does not show evidence {eid} "
            "(url/quote or paper/anchor differ)"
        )


def _map_credit(
    bid: str,
    visual: dict[str, Any],
    captures: dict[str, dict[str, Any]] | None,
    report: ScriptReport,
) -> None:
    """A map scene carries a map credit: its own, or one its captures recorded."""
    texts = [visual.get("credit", "")]
    pending = False
    for cid in _capture_ids_in(visual["props"]):
        if captures is not None and cid in captures:
            texts.extend(captures[cid]["credits"])
        else:
            pending = True
    if any(credit in text for text in texts for credit in MAP_CREDITS):
        return
    if pending:
        report.deferred.append(f"{bid}: map credit checked after capture")
        return
    report.errors.append(f"{bid}: a map scene carries the in-frame credit {list(MAP_CREDITS)}")


def _clip_length(bid: str, props: dict[str, Any], seconds: float, report: ScriptReport) -> None:
    """The renderer refuses a clip that ends before its scene (video/src/blocks/clips.ts)."""
    clip = props["clip"]
    start = props.get("start_s", 0)
    need = start + math.ceil(round(seconds * FPS, 6)) / FPS
    if need > clip["duration_s"] + 1e-6:
        report.errors.append(
            f"{bid}: capture {clip['id']} is {clip['duration_s']} s long; the scene needs "
            f"{need:.3f} s from {start} s (record a longer take or shorten the beat)"
        )


def _spine(
    beats: list[dict[str, Any]],
    blocks_used: list[str],
    hook_beats: int,
    roles: dict[str, int],
    report: ScriptReport,
) -> None:
    """Spec 4.10's common spine of every full episode (slices are exempt)."""
    last = beats[-1]
    visual = last.get("visual") if isinstance(last, dict) else None
    last_block = visual.get("block") if isinstance(visual, dict) else None
    lacks = []
    if not hook_beats:
        lacks.append("a hook beat")
    for block in ("ClaimBoard", "Meter"):
        if block not in blocks_used:
            lacks.append(f"a {block} beat")
    if not {"EvidenceCard", "SourceViewer"} & set(blocks_used):
        lacks.append("an EvidenceCard or SourceViewer beat")
    if last_block != "ShareCard":
        lacks.append("a closing ShareCard beat")
    lacks.extend(f"a beat with role {role!r}" for role in ROLES if role not in roles)
    report.errors.extend(f"full episode lacks {what}" for what in lacks)
    order = [roles[r] for r in ROLES if r in roles]
    if len(order) == len(ROLES) and order != sorted(order):
        report.errors.append(f"full episode needs the roles {', '.join(ROLES)} in that order")


def _chapters(
    script: dict[str, Any],
    beats: list[dict[str, Any]],
    words: dict[str, Any] | None,
    fmt: str,
    report: ScriptReport,
) -> None:
    order = [b["id"] for b in beats if isinstance(b, dict) and "id" in b]
    chapters = script["chapters"]
    if not isinstance(chapters, list) or not chapters:
        report.errors.append("chapters must be a non-empty list")
        return
    starts = []
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict) or set(ch) != {"title", "beat"} or ch["beat"] not in order:
            report.errors.append(f"chapter {ch!r}: must be {{title, beat}} naming an existing beat")
            return
        if not isinstance(ch["title"], str) or not ch["title"].strip():
            report.errors.append(f"chapter {ch!r}: title must be a non-empty string")
            return
        problem = glyph_problem(f"chapters[{i}].title", ch["title"])
        if problem is not None:
            report.errors.append(problem)
        starts.append(order.index(ch["beat"]))
    if starts[0] != 0:
        report.errors.append("the first chapter must start at the first beat (0:00)")
    if starts != sorted(set(starts)):
        report.errors.append("chapters must start at distinct beats in beat order")
        return
    if fmt == "full" and len(chapters) < CHAPTERS_MIN_FULL:
        report.errors.append(f"a full episode has at least {CHAPTERS_MIN_FULL} chapters")
    if words is None:
        report.deferred.append("chapter lengths are checked after the voice step")
        return
    bounds = [*starts, len(beats)]
    for ch, a, b in zip(chapters, bounds, bounds[1:], strict=False):
        seconds = sum(scene_seconds(beat, speech_seconds(beat, words)) for beat in beats[a:b])
        if seconds < CHAPTER_MIN_S:
            report.errors.append(
                f"chapter {ch['title']!r} lasts {seconds:.1f} s (min {CHAPTER_MIN_S:.0f} s)"
            )

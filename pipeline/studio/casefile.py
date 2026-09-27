"""The case file (spec 4.2): the verified evidence an episode may show, as a typed model.

Claude authors episodes/<slug>/casefile.json; `load_casefile` parses it strictly (unknown or
missing keys, wrong types) and validates the rules:
- every id is unique across claims, evidence, places, quantities, media and markers;
- a quantity given as a range [lo, hi] states the basis ("sources differ: ...");
- a marker is `verified: "crop-check"` (its box was checked on a crop of the image; the
  accepted check itself is markers.py's, per image and box);
- a claim's icon is one of the renderer's ClaimBoard icons (registry.json, passed in);
- a place names its coord_source; media carry licence, attribution and source URL, and a clean
  path under media/ (`asset_path_problem`, the renderer's rule);
- photorealistic AI imagery (`ai_generated: true`) is refused unless the episode allows it.
"Every evidence item the script uses is verified" is checked by script.py, which knows the use.
`claims[].status` is the status the ClaimBoard shows before the first `status` cue for that
claim (normally "pending"; script.py requires "pending" for every claim on a board): verdicts
are set only by `status` cues, never in the case file.

Script props reference case-file entities as {"$ref": "<id>"} and captures as
{"$capture": "<id>"}; `resolve_refs` replaces them with the shapes in `resolved()` /
the capture manifest, paths relative to the per-render public dir.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE
from pipeline.studio.config import REQUEST_ID_RE, SHA256_RE
from pipeline.studio.errors import StudioError

TOPIC_TYPES = ("A", "B", "C", "D")
CLAIM_STATUSES = ("pending", "supported", "weakened", "refuted", "open")
EVIDENCE_KINDS = ("fact", "quote", "quantity", "date", "image", "place")
VERIFICATION_STATUSES = ("verified", "unverified", "refuted")
MARKER_CHECK = "crop-check"
_NUM = (int, float)
#: Where a public-dir src may live (the renderer's ASSET_DIRS, video/src/timeline.ts).
ASSET_DIRS = ("voice", "captures", "media", "music")


class CaseFileError(StudioError):
    """casefile.json is malformed or breaks a rule; the message lists every problem."""


class CaptureNotRecorded(StudioError):
    """A {"$capture": id} ref was resolved before that capture was recorded."""


def asset_path_problem(src: str) -> str | None:
    """Why `src` is not a clean public-dir path (the renderer's assetProblem); None when it is."""
    parts = src.split("/")
    if parts[0] not in ASSET_DIRS or len(parts) < 2:
        return f'"{src}" must lie under ' + ", ".join(f"{d}/" for d in ASSET_DIRS)
    if "\\" in src or ":" in src or any(p in ("", ".", "..") for p in parts):
        return f'"{src}" is not a clean relative path'
    return None


@dataclass(frozen=True)
class PaperRef:
    request_id: str
    slug: str
    report_sha256: str


@dataclass(frozen=True)
class Claim:
    id: str
    label: str
    by: str
    icon: str
    status: str


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    tier: int
    license: str
    quote: str
    locator: str
    source_id: str | None = None


@dataclass(frozen=True)
class Verification:
    status: str
    by: str
    at: str
    method: str


@dataclass(frozen=True)
class Evidence:
    id: str
    claim_id: str
    kind: str
    statement: str
    source: Source
    paper_anchor: str | None
    verification: Verification


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    lat: float
    lng: float
    site_id: str | None
    coord_source: str


@dataclass(frozen=True)
class Quantity:
    id: str
    label: str
    value: float | list[float]
    unit: str
    basis: str
    evidence: list[str]


@dataclass(frozen=True)
class Marker:
    id: str
    box: list[float]
    label: str
    verified: str


@dataclass(frozen=True)
class Media:
    id: str
    path: str
    license: str
    attribution: str
    source_url: str
    depicts: str
    markers: list[Marker]
    ai_generated: bool = False


@dataclass(frozen=True)
class Meter:
    hypotheses: list[str]
    start: list[int]


@dataclass(frozen=True)
class CaseFile:
    version: int
    paper: PaperRef | None
    topic_type: str
    claims: list[Claim]
    evidence: list[Evidence]
    places: list[Place]
    quantities: list[Quantity]
    media: list[Media]
    meter: Meter

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _obj(
    data: Any,
    path: str,
    required: dict[str, tuple[type, ...]],
    optional: dict[str, tuple[type, ...]] | None = None,
) -> dict[str, Any]:
    optional = optional or {}
    if not isinstance(data, dict):
        raise CaseFileError(f"{path}: must be an object")
    unknown = sorted(set(data) - set(required) - set(optional))
    if unknown:
        raise CaseFileError(f"{path}: unknown keys {unknown}")
    for key, types in {**required, **optional}.items():
        if key not in data:
            if key in required:
                raise CaseFileError(f"{path}.{key}: missing")
            continue
        value = data[key]
        numeric_only = all(t in _NUM for t in types)
        if not isinstance(value, types) or (numeric_only and isinstance(value, bool)):
            raise CaseFileError(f"{path}.{key}: expected {[t.__name__ for t in types]}")
    return data


def _list(data: dict[str, Any], key: str, path: str) -> list[Any]:
    value = data[key]
    if not isinstance(value, list):
        raise CaseFileError(f"{path}.{key}: must be a list")
    return value


def from_dict(data: Any) -> CaseFile:
    d = _obj(
        data,
        "casefile",
        {
            "version": (int,),
            "paper": (dict, type(None)),
            "topic_type": (str,),
            "claims": (list,),
            "evidence": (list,),
            "places": (list,),
            "quantities": (list,),
            "media": (list,),
            "meter": (dict,),
        },
    )
    paper = None
    if d["paper"] is not None:
        p = _obj(
            d["paper"], "paper", {"request_id": (str,), "slug": (str,), "report_sha256": (str,)}
        )
        paper = PaperRef(p["request_id"], p["slug"], p["report_sha256"])
    claims = []
    for i, c in enumerate(_list(d, "claims", "casefile")):
        c = _obj(c, f"claims[{i}]", dict.fromkeys(("id", "label", "by", "icon", "status"), (str,)))
        claims.append(Claim(**c))
    evidence = []
    for i, e in enumerate(_list(d, "evidence", "casefile")):
        where = f"evidence[{i}]"
        e = _obj(
            e,
            where,
            {
                "id": (str,),
                "claim_id": (str,),
                "kind": (str,),
                "statement": (str,),
                "source": (dict,),
                "paper_anchor": (str, type(None)),
                "verification": (dict,),
            },
        )
        s = _obj(
            e["source"],
            f"{where}.source",
            {
                "url": (str,),
                "title": (str,),
                "tier": (int,),
                "license": (str,),
                "quote": (str,),
                "locator": (str,),
            },
            {"source_id": (str, type(None))},
        )
        v = _obj(
            e["verification"],
            f"{where}.verification",
            {"status": (str,), "by": (str,), "at": (str,), "method": (str,)},
        )
        evidence.append(
            Evidence(
                id=e["id"],
                claim_id=e["claim_id"],
                kind=e["kind"],
                statement=e["statement"],
                source=Source(**s),
                paper_anchor=e["paper_anchor"],
                verification=Verification(**v),
            )
        )
    places = []
    for i, p in enumerate(_list(d, "places", "casefile")):
        p = _obj(
            p,
            f"places[{i}]",
            {
                "id": (str,),
                "name": (str,),
                "lat": _NUM,
                "lng": _NUM,
                "site_id": (str, type(None)),
                "coord_source": (str,),
            },
        )
        places.append(Place(**p))
    quantities = []
    for i, q in enumerate(_list(d, "quantities", "casefile")):
        q = _obj(
            q,
            f"quantities[{i}]",
            {
                "id": (str,),
                "label": (str,),
                "value": (int, float, list),
                "unit": (str,),
                "basis": (str,),
                "evidence": (list,),
            },
        )
        quantities.append(Quantity(**q))
    media = []
    for i, m in enumerate(_list(d, "media", "casefile")):
        where = f"media[{i}]"
        m = _obj(
            m,
            where,
            {
                "id": (str,),
                "path": (str,),
                "license": (str,),
                "attribution": (str,),
                "source_url": (str,),
                "depicts": (str,),
                "markers": (list,),
            },
            {"ai_generated": (bool,)},
        )
        markers = []
        for j, mk in enumerate(m["markers"]):
            mk = _obj(
                mk,
                f"{where}.markers[{j}]",
                {"id": (str,), "box": (list,), "label": (str,), "verified": (str,)},
            )
            markers.append(Marker(**mk))
        media.append(Media(**{**m, "markers": markers}))
    mt = _obj(d["meter"], "meter", {"hypotheses": (list,), "start": (list,)})
    return CaseFile(
        version=d["version"],
        paper=paper,
        topic_type=d["topic_type"],
        claims=claims,
        evidence=evidence,
        places=places,
        quantities=quantities,
        media=media,
        meter=Meter(mt["hypotheses"], mt["start"]),
    )


def _box_ok(box: list[Any]) -> bool:
    return (
        len(box) == 4
        and all(isinstance(v, _NUM) and not isinstance(v, bool) and 0 <= v <= 1 for v in box)
        and box[2] > 0
        and box[3] > 0
        and box[0] + box[2] <= 1
        and box[1] + box[3] <= 1
    )


def validate(cf: CaseFile, *, icons: Sequence[str], allow_ai_imagery: bool = False) -> list[str]:
    """Every rule the case file breaks; `icons` are the renderer's ClaimBoard icon names."""
    problems: list[str] = []
    if cf.version != 1:
        problems.append(f"version {cf.version}; expected 1")
    if cf.topic_type not in TOPIC_TYPES:
        problems.append(f"topic_type must be one of {list(TOPIC_TYPES)}")
    if cf.paper is not None:
        if not REQUEST_ID_RE.fullmatch(cf.paper.request_id):
            problems.append("paper.request_id is not a request uuid")
        if not SHA256_RE.fullmatch(cf.paper.report_sha256):
            problems.append("paper.report_sha256 is not a sha256")
    ids = (
        [c.id for c in cf.claims]
        + [e.id for e in cf.evidence]
        + [p.id for p in cf.places]
        + [q.id for q in cf.quantities]
        + [m.id for m in cf.media]
        + [mk.id for m in cf.media for mk in m.markers]
    )
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"duplicate ids {dupes}")
    claim_ids = {c.id for c in cf.claims}
    evidence_ids = {e.id for e in cf.evidence}
    for c in cf.claims:
        if c.status not in CLAIM_STATUSES:
            problems.append(f"{c.id}: status must be one of {list(CLAIM_STATUSES)}")
        if c.icon not in icons:
            problems.append(f"{c.id}: icon {c.icon!r} is not one of {', '.join(icons)}")
    for e in cf.evidence:
        if e.claim_id not in claim_ids:
            problems.append(f"{e.id}: claim_id {e.claim_id} is not a claim")
        if e.kind not in EVIDENCE_KINDS:
            problems.append(f"{e.id}: kind must be one of {list(EVIDENCE_KINDS)}")
        if not e.source.url.startswith(("http://", "https://")):
            problems.append(f"{e.id}: source.url must be http(s)")
        if e.paper_anchor is not None and not EVIDENCE_ID_RE.fullmatch(e.paper_anchor):
            problems.append(f"{e.id}: paper_anchor must be ev-NN or null")
        v = e.verification
        if v.status not in VERIFICATION_STATUSES:
            problems.append(
                f"{e.id}: verification.status must be one of {list(VERIFICATION_STATUSES)}"
            )
        elif v.status == "verified" and not (v.by.strip() and v.at.strip() and v.method.strip()):
            problems.append(f"{e.id}: a verified item names by, at and method")
    for p in cf.places:
        if not (-90 <= p.lat <= 90 and -180 <= p.lng <= 180):
            problems.append(f"{p.id}: coordinates out of range")
        if not p.coord_source.strip():
            problems.append(f"{p.id}: coord_source is required")
    for q in cf.quantities:
        if isinstance(q.value, list):
            if not (
                len(q.value) == 2
                and all(isinstance(v, _NUM) and not isinstance(v, bool) for v in q.value)
                and q.value[0] < q.value[1]
            ):
                problems.append(f"{q.id}: a range is [low, high] with low < high")
            elif not q.basis.strip():
                problems.append(f"{q.id}: a range must state its basis (sources differ)")
        missing = [x for x in q.evidence if x not in evidence_ids]
        if missing or not q.evidence:
            problems.append(f"{q.id}: evidence must list existing evidence ids (missing {missing})")
    for m in cf.media:
        path_problem = asset_path_problem(m.path)
        if path_problem is not None:
            problems.append(f"{m.id}: {path_problem}")
        elif not m.path.startswith("media/"):
            problems.append(f"{m.id}: path must be relative under media/")
        for key in ("license", "attribution", "source_url"):
            if not getattr(m, key).strip():
                problems.append(f"{m.id}: {key} is required")
        if m.ai_generated and not allow_ai_imagery:
            problems.append(f"{m.id}: AI-generated imagery is not allowed in this episode")
        for mk in m.markers:
            if mk.verified != MARKER_CHECK:
                problems.append(f"{mk.id}: a marker must be verified by {MARKER_CHECK!r}")
            if not _box_ok(mk.box):
                problems.append(f"{mk.id}: box must be [x, y, w, h] fractions inside the image")
    hyps, start = cf.meter.hypotheses, cf.meter.start
    if len(hyps) != 2 or not all(isinstance(h, str) and h.strip() for h in hyps):
        problems.append("meter.hypotheses must be two non-empty strings")
    if (
        len(start) != 2
        or not all(isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 100 for s in start)
        or sum(start) != 100
    ):
        problems.append("meter.start must be two integers 0-100 summing to 100")
    return problems


def load_casefile(path: Path, *, icons: Sequence[str], allow_ai_imagery: bool = False) -> CaseFile:
    if not path.exists():
        raise CaseFileError(f"{path} does not exist: write the case file first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseFileError(f"casefile.json is not valid JSON: {exc}") from exc
    cf = from_dict(data)
    problems = validate(cf, icons=icons, allow_ai_imagery=allow_ai_imagery)
    if problems:
        raise CaseFileError("; ".join(problems))
    return cf


def resolved(cf: CaseFile) -> dict[str, dict[str, Any]]:
    """Every referencable entity by id, in the shape blocks receive."""
    out: dict[str, dict[str, Any]] = {}
    for c in cf.claims:
        out[c.id] = {"id": c.id, "label": c.label, "by": c.by, "icon": c.icon, "status": c.status}
    for e in cf.evidence:
        s = e.source
        out[e.id] = {
            "id": e.id,
            "claim_id": e.claim_id,
            "kind": e.kind,
            "statement": e.statement,
            "source": {
                "url": s.url,
                "title": s.title,
                "tier": s.tier,
                "license": s.license,
                "quote": s.quote,
                "locator": s.locator,
            },
            "paper_anchor": e.paper_anchor,
        }
    for p in cf.places:
        out[p.id] = {"id": p.id, "name": p.name, "lat": p.lat, "lng": p.lng, "site_id": p.site_id}
    for q in cf.quantities:
        out[q.id] = {
            "id": q.id,
            "label": q.label,
            "value": q.value,
            "unit": q.unit,
            "basis": q.basis,
        }
    for m in cf.media:
        out[m.id] = {
            "id": m.id,
            "src": m.path,
            "license": m.license,
            "attribution": m.attribution,
            "source_url": m.source_url,
            "depicts": m.depicts,
            "markers": [{"id": k.id, "box": k.box, "label": k.label} for k in m.markers],
        }
    return out


def capture_ref(manifest: dict[str, Any]) -> dict[str, Any]:
    """A capture manifest in the shape blocks receive (`path` becomes `src`)."""
    return {
        "id": manifest["id"],
        "kind": manifest["kind"],
        "src": manifest["path"],
        "fps": manifest["fps"],
        "duration_s": manifest["duration_s"],
        "width": manifest["width"],
        "height": manifest["height"],
        "events": manifest["events"],
        "credits": manifest["credits"],
    }


def resolve_refs(
    value: Any, entities: dict[str, dict[str, Any]], captures: dict[str, dict[str, Any]] | None
) -> Any:
    """Replace {"$ref": id} and {"$capture": id} anywhere inside `value`.

    A capture without a (current) manifest is CaptureNotRecorded: the check waits for
    `episode capture`; whether the id is declared at all is script.py's check.
    """
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            ref = value["$ref"]
            if ref not in entities:
                raise CaseFileError(f"$ref {ref!r} is not in the case file")
            return entities[ref]
        if set(value) == {"$capture"}:
            cid = value["$capture"]
            if captures is None or cid not in captures:
                raise CaptureNotRecorded(f"capture {cid!r} is not recorded yet")
            return capture_ref(captures[cid])
        return {k: resolve_refs(v, entities, captures) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(v, entities, captures) for v in value]
    return value


def refs_in(value: Any) -> list[str]:
    """Every case-file id a props value references with {"$ref": id}."""
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            return [value["$ref"]]
        return [r for v in value.values() for r in refs_in(v)]
    if isinstance(value, list):
        return [r for v in value for r in refs_in(v)]
    return []

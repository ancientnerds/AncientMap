"""The renderer's registry entries, a valid script and word timings for the script tests.

REGISTRY is the literal registry.json entry (stream D's video/src/blocks/schemas.ts, contract
C5) of every block these tests use, built with the same helpers schemas.ts uses; Task 27
checks it against the committed video/src/blocks/registry.json.
"""

from __future__ import annotations

import copy

ICONS = ["weight", "ruler", "clock", "globe", "tool", "eye", "scroll", "star", "question", "people"]
CLAIM_STATUSES = ["pending", "supported", "weakened", "refuted", "open"]
TONES = ["accent", "info", "warn", "alert", "muted"]


def _str(min_length: int = 1, max_length: int | None = None) -> dict:
    schema = {"type": "string", "minLength": min_length}
    if max_length is not None:
        schema["maxLength"] = max_length
    return schema


def _num(minimum: float | None = None, maximum: float | None = None, kind: str = "number") -> dict:
    schema: dict = {"type": kind}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _one_of(values: list[str]) -> dict:
    return {"type": "string", "enum": values}


def _arr(items: dict, min_items: int | None = None, max_items: int | None = None) -> dict:
    schema: dict = {"type": "array", "items": items}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def _obj(properties: dict, required: list[str] | None = None, description: str | None = None):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties) if required is None else required,
        "properties": properties,
    }
    if description is not None:
        schema["description"] = description
    return schema


ID = _str(1, 64)
ASSET = _str(1, 240)
TITLE = _str(1, 44)
LIST_TITLE = _str(1, 42)
LABEL = _obj({"title": _str(1, 24), "subtitle": _str(1, 49)}, ["title"], "Lower third over footage")
MEDIA = _obj(
    {
        "id": ID,
        "src": ASSET,
        "license": _str(1),
        "attribution": _str(1),
        "source_url": _str(1),
        "depicts": _str(1),
        "markers": _arr(
            _obj({"id": ID, "box": _arr(_num(0, 1), 4, 4), "label": _str(1, 24)}), 0, 6
        ),
    }
)
CLAIM = _obj(
    {
        "id": ID,
        "label": _str(1, 66),
        "by": _str(0, 40),
        "icon": {
            **_one_of(ICONS),
            "description": "ClaimBoard icon; the case file must use one of these names",
        },
        "status": _one_of(CLAIM_STATUSES),
    }
)
EVENT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["t", "name"],
    "properties": {
        "t": _num(0),
        "name": _str(1),
        "x": _num(),
        "y": _num(),
        "box": _arr(_num(), 4, 4),
        "target": _str(1),
        "label": _str(1),
        "url": _str(1),
        "title": _str(0),
        "lat": _num(-90, 90),
        "lng": _num(-180, 180),
        "track": {
            "type": "array",
            "items": {
                "type": ["array", "null"],
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "description": "Globe place events: the pixel [x, y] in every capture frame from the event on, null while hidden",
        },
    },
}
CLIP_START = {**_num(0), "description": "Seconds into the clip where the scene starts (default 0)"}
BASIS = {
    **_str(3, 95),
    "description": "What the comparison is based on, always shown on screen (owner rule)",
}


def evidence_schema(
    statement: int | None = None,
    quote: int | None = None,
    title: int | None = None,
    locator: int | None = None,
) -> dict:
    source = {
        "url": _str(1),
        "title": _str(1, title),
        "tier": _num(0, kind="integer"),
        "license": _str(0),
        "quote": _str(0, quote),
        "locator": _str(0, locator),
    }
    return _obj(
        {
            "id": ID,
            "claim_id": ID,
            "kind": _one_of(["fact", "quote", "quantity", "date", "image", "place"]),
            "statement": _str(1, statement),
            "source": _obj(source),
            "paper_anchor": {"type": ["string", "null"]},
        }
    )


def capture_schema(kind: str, still: bool) -> dict:
    return _obj(
        {
            "id": ID,
            "kind": _one_of([kind]),
            "src": ASSET,
            "fps": {"type": "null"} if still else _num(1),
            "duration_s": {"type": "null"} if still else _num(0),
            "width": _num(2, kind="integer"),
            "height": _num(2, kind="integer"),
            "events": _arr(EVENT),
            "credits": _arr(_str(1)),
        }
    )


def _entry(props: dict, drawn: list[str], *, map_: bool = False, platform: bool = False) -> dict:
    return {"map": map_, "platform": platform, "props": props, "drawn": drawn}


LABEL_DRAWN = ["label.title", "label.subtitle"]
QUANTITY_END = _obj(
    {
        "id": ID,
        "label": _str(1, 32),
        "value": {**_num(0), "description": "Greater than 0, in the chart unit"},
    }
)

REGISTRY = {
    "PhotoPlate": _entry(
        _obj(
            {
                "image": MEDIA,
                "kenBurns": {
                    **_one_of(["in", "out", "none"]),
                    "description": "Camera over the whole scene (default in)",
                },
                "label": LABEL,
                "caption": _str(1, 51),
            },
            ["image"],
            "A checked photo with its markers in the same moving layer; cues show/hide/highlight <marker id>",
        ),
        [*LABEL_DRAWN, "caption", "image.markers[].label"],
    ),
    "PlatformClip": _entry(
        _obj(
            {
                "clip": capture_schema("platform", False),
                "start_s": CLIP_START,
                "camera": {
                    **_arr(
                        _obj({"t": _num(0), "cx": _num(0), "cy": _num(0), "zoom": _num(1, 3)}), 1
                    ),
                    "description": "Virtual camera keys on the capture clock (t in clip seconds, cx/cy in capture pixels)",
                },
                "follow": {
                    **_num(1, 2.5),
                    "description": "Zoom the virtual camera onto each event with x/y (instead of camera)",
                },
                "label": LABEL,
            },
            ["clip"],
            "A platform moment: the real ancientnerds.com recorded by the capture step",
        ),
        LABEL_DRAWN,
        map_=True,
        platform=True,
    ),
    "MapboxFlyover": _entry(
        _obj(
            {"clip": capture_schema("globe", False), "start_s": CLIP_START, "label": LABEL},
            ["clip"],
            "A Mapbox fly-in or orbit take",
        ),
        LABEL_DRAWN,
        map_=True,
    ),
    "EvidenceCard": _entry(
        _obj(
            {"evidence": evidence_schema(100, 220, 66, 24), "image": MEDIA},
            ["evidence"],
            "One verified evidence item; cues highlight <evidence id> (quote types on), stamp <evidence id>",
        ),
        [
            "evidence.kind",
            "evidence.statement",
            "evidence.source.quote",
            "evidence.source.title",
            "evidence.source.locator",
        ],
    ),
    "SourceViewer": _entry(
        _obj(
            {"page": capture_schema("source", True), "evidence": evidence_schema(160)},
            ["page", "evidence"],
            "A captured source page with the quote highlighted; cue highlight <evidence id>",
        ),
        [],
    ),
    "ClaimBoard": _entry(
        _obj(
            {"claims": _arr(CLAIM, 1, 6), "title": TITLE},
            ["claims"],
            "The claims under test; introduce/status cues (any scene) drive it; cue highlight <claim id>",
        ),
        ["title", "claims[].label", "claims[].by"],
    ),
    "Meter": _entry(
        _obj(
            {
                "hypotheses": _arr(_str(1, 40), 2, 2),
                "start": {
                    **_arr(_num(0, 100, kind="integer"), 2, 2),
                    "description": "Split before the first meter cue; sums to 100",
                },
                "title": TITLE,
                "note": _str(1, 110),
            },
            ["hypotheses", "start"],
            "The probability meter; meter cues (any scene) move it",
        ),
        ["title", "hypotheses[]", "note"],
    ),
    "BarChart": _entry(
        _obj(
            {
                "title": TITLE,
                "unit": _str(1, 6),
                "basis": BASIS,
                "bars": _arr(
                    _obj(
                        {
                            "id": ID,
                            "label": _str(1, 32),
                            "value": {
                                "type": ["number", "array"],
                                "minimum": 0,
                                "items": _num(0),
                                "minItems": 2,
                                "maxItems": 2,
                                "description": "a number, or [low, high] when sources differ (the bar shows the range)",
                            },
                            "tone": _one_of(TONES),
                        },
                        ["id", "label", "value"],
                    ),
                    2,
                    8,
                ),
            },
            ["title", "unit", "basis", "bars"],
            "Horizontal bars on a linear axis (frequencies, sizes); a [low, high] value is drawn as a range; cue show <bar id>",
        ),
        ["title", "unit", "basis", "bars[].label"],
    ),
    "ScaleZoom": _entry(
        _obj(
            {
                "title": TITLE,
                "unit": _str(1, 16),
                "basis": BASIS,
                "small": QUANTITY_END,
                "large": QUANTITY_END,
            },
            None,
            "A linear zoom-out for ratios beyond a UnitGrid (1:400), never a log axis: the small quantity drawn readable, then the camera pulls back linearly until the large one fits, the small one shrinking to a dot; cue show <small id> or show <large id> (the quantity appears)",
        ),
        ["title", "unit", "basis", "small.label", "large.label"],
    ),
    "ListCard": _entry(
        _obj(
            {
                "title": LIST_TITLE,
                "items": _arr(_obj({"id": ID, "text": _str(1, 72)}), 1, 5),
                "note": _str(1, 110),
            },
            ["title", "items"],
            "A short list, e.g. what would change our mind; cue show <item id>",
        ),
        ["title", "items[].text", "note"],
    ),
    "ShareCard": _entry(
        _obj(
            {"headline": _str(1, 50), "url": _str(1, 43), "lines": _arr(_str(1, 66), 0, 3)},
            None,
            "The end card: the one place the link appears in the picture",
        ),
        ["headline", "url", "lines[]"],
    ),
}


def beat(bid: str, spoken: str, block: str, props: dict, **extra) -> dict:
    b = {
        "id": bid,
        "spoken": spoken,
        "display": extra.pop("display", spoken),
        "evidence": extra.pop("evidence", ["e1"]),
        "visual": {"block": block, "props": props},
        "cues": extra.pop("cues", []),
        "min_s": extra.pop("min_s", 3.0),
    }
    credit = extra.pop("credit", None)
    if credit is not None:
        b["visual"]["credit"] = credit
    b.update(extra)
    return b


def script() -> dict:
    clip = lambda n: {"clip": {"$capture": f"platform-0{n}"}}  # noqa: E731
    return {
        "version": 1,
        "episode": "baalbek-c5",
        "fps": 60,
        "voice": {"id": "English_expressive_narrator", "speed": 1.0},
        "captures": [
            {
                "id": f"platform-0{n}",
                "kind": "platform",
                "target": "local",
                "actions": [{"do": "search", "q": "Baalbek"}],
            }
            for n in (1, 2, 3)
        ],
        "beats": [
            beat(
                "b01",
                "This stone weighs about a thousand tonnes. One person gives the scale.",
                "PhotoPlate",
                {"image": {"$ref": "m1"}, "kenBurns": "in"},
                display="This stone weighs about 1,000 tonnes. One person gives the scale.",
                hook=True,
                cues=[{"at_word": "person", "do": "show", "target": "mk1"}],
            ),
            beat(
                "b02",
                "Some say no one could move it without machines.",
                "ClaimBoard",
                {"claims": [{"$ref": "c1"}]},
                hook=True,
                factual=False,
                evidence=[],
                cues=[{"at_word": "machines", "do": "introduce", "target": "c1"}],
            ),
            beat(
                "b03",
                "Here is the quarry on our globe.",
                "PlatformClip",
                clip(1),
                credit="© Mapbox © Maxar",
                min_s=5.0,
            ),
            beat(
                "b04",
                "The block still lies where it was cut.",
                "PlatformClip",
                clip(2),
                credit="© Mapbox © Maxar",
                min_s=5.0,
            ),
            beat(
                "b05",
                "The podium stones sit a short walk away.",
                "PlatformClip",
                clip(3),
                credit="© Mapbox © Maxar",
                min_s=5.0,
                role="twist",
            ),
            beat(
                "b06",
                "The excavators measured it in the quarry.",
                "EvidenceCard",
                {"evidence": {"$ref": "e1"}},
                cues=[{"at_word": "measured", "do": "status", "target": "c1", "value": "weakened"}],
            ),
            beat(
                "b07",
                "So the balance tips toward Roman engineers.",
                "Meter",
                {
                    "hypotheses": ["Roman engineers", "An older, lost civilization"],
                    "start": [50, 50],
                },
                factual=False,
                evidence=[],
                role="verdict",
                cues=[{"at_word": "Roman", "do": "meter", "target": "meter", "value": [70, 30]}],
            ),
            beat(
                "b08",
                "Only a tool mark older than Rome would change our mind.",
                "ListCard",
                {
                    "title": "What would change our mind",
                    "items": [{"id": "i1", "text": "A tool mark dated before Rome"}],
                },
                factual=False,
                evidence=[],
                role="change_mind",
                cues=[{"at_word": "tool", "do": "show", "target": "i1"}],
            ),
            beat(
                "b09",
                "The whole case file is on our site.",
                "ShareCard",
                {
                    "headline": "Who moved the Baalbek stones?",
                    "url": "ancientnerds.com",
                    "lines": [],
                },
                factual=False,
                evidence=[],
            ),
        ],
        "chapters": [
            {"title": "The stone", "beat": "b01"},
            {"title": "On the globe", "beat": "b03"},
            {"title": "The verdict", "beat": "b06"},
        ],
        "thumbnails": [
            {"beat": "b01", "at": 0.6, "text": "Who moved it?"},
            {"beat": "b04", "at": 0.5, "text": "A thousand tonnes?"},
            {"beat": "b06", "at": 0.1, "text": "Lifted by hand?"},
        ],
    }


def mutated_script(mutate) -> dict:
    data = copy.deepcopy(script())
    mutate(data)
    return data


def words_for(data: dict, seconds_per_beat: float = 5.0) -> dict:
    """words.json for `data`: display words spread evenly over each beat's speech."""
    out = {}
    for b in data["beats"]:
        tokens = b["display"].split()
        step = seconds_per_beat / len(tokens)
        out[b["id"]] = {
            "duration_s": seconds_per_beat,
            "words": [
                {"w": t, "s": round(i * step, 3), "e": round((i + 1) * step - 0.05, 3)}
                for i, t in enumerate(tokens)
            ],
        }
    return out


def voice_manifest(data: dict | None = None, seconds_per_beat: float = 5.0) -> dict:
    """voice/manifest.json as `episode voice` leaves it for `data` (see voice.py)."""
    import hashlib

    data = data or script()
    sha = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()  # noqa: E731
    words = words_for(data, seconds_per_beat)
    return {
        b["id"]: {
            "spoken_sha256": sha(b["spoken"]),
            "voice_id": data["voice"]["id"],
            "speed": float(data["voice"]["speed"]),
            "duration_s": words[b["id"]]["duration_s"],
            "display_sha256": sha(b["display"]),
            "words": words[b["id"]]["words"],
        }
        for b in data["beats"]
    }


def stored_manifests(data: dict | None = None) -> dict:
    """captures/<id>.json as `episode capture` stores them: manifest + spec_sha256."""
    from pipeline.studio.episode import capture_spec_sha256

    specs = {c["id"]: c for c in (data or script())["captures"]}
    return {
        cid: {**manifest, "spec_sha256": capture_spec_sha256(specs[cid])}
        for cid, manifest in manifests().items()
    }


def manifests() -> dict:
    return {
        f"platform-0{n}": {
            "id": f"platform-0{n}",
            "kind": "platform",
            "path": f"captures/platform-0{n}.mp4",
            "fps": 60,
            "duration_s": 8.0,
            "width": 1920,
            "height": 1080,
            "events": [{"t": 0.4, "name": "search"}],
            "credits": ["© Mapbox © Maxar"],
        }
        for n in (1, 2, 3)
    }

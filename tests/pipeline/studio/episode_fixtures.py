"""Builders for the video-studio tests: a case file, its media and marker checks, the paper."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path

REQ = "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
#: The renderer's ClaimBoard icons (registry.json ClaimBoard.props...claims.items...icon.enum).
ICONS = ("weight", "ruler", "clock", "globe", "tool", "eye", "scroll", "star", "question", "people")


def casefile() -> dict:
    return {
        "version": 1,
        "paper": {
            "request_id": REQ,
            "slug": "the-megaliths",
            "report_sha256": "a" * 64,
        },
        "topic_type": "A",
        "claims": [
            {
                "id": "c1",
                "label": "No one could move 800 t without machines",
                "by": "core claim",
                "icon": "weight",
                "status": "pending",
            }
        ],
        "evidence": [
            {
                "id": "e1",
                "claim_id": "c1",
                "kind": "quantity",
                "statement": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
                "source": {
                    "url": "https://www.dainst.org/baalbek-report",
                    "title": "DAI report",
                    "source_id": "aaaaaaaaaaa1",
                    "tier": 1,
                    "license": "",
                    "quote": "weighs about 1000 tons",
                    "locator": "p. 3",
                },
                "paper_anchor": "ev-01",
                "verification": {
                    "status": "verified",
                    "by": "claude-opus-5-5",
                    "at": "2026-09-26",
                    "method": "archived text",
                },
            },
            {
                "id": "e2",
                "claim_id": "c1",
                "kind": "fact",
                "statement": "Romans moved 800-tonne blocks onto the podium.",
                "source": {
                    "url": "https://en.wikipedia.org/wiki/Baalbek",
                    "title": "Baalbek",
                    "tier": 2,
                    "license": "CC BY-SA 4.0",
                    "quote": "800 tons blocks",
                    "locator": "Temple of Jupiter",
                },
                "paper_anchor": None,
                "verification": {"status": "unverified", "by": "", "at": "", "method": ""},
            },
        ],
        "places": [
            {
                "id": "p1",
                "name": "Baalbek quarry",
                "lat": 33.99917,
                "lng": 36.20028,
                "site_id": None,
                "coord_source": "Wikipedia coordinates",
            }
        ],
        "quantities": [
            {
                "id": "q1",
                "label": "2014 block",
                "value": [1500, 1650],
                "unit": "t",
                "basis": "sources differ: DAI 2014 vs Wikipedia",
                "evidence": ["e1"],
            }
        ],
        "media": [
            {
                "id": "m1",
                "path": "media/stone_person.jpg",
                "license": "CC BY-SA 4.0",
                "attribution": "Jane Doe",
                "source_url": "https://commons.wikimedia.org/wiki/File:Stone.jpg",
                "depicts": "the Stone of the Pregnant Woman with a person for scale",
                "markers": [
                    {
                        "id": "mk1",
                        "box": [0.1, 0.5, 0.1, 0.3],
                        "label": "1 PERSON",
                        "verified": "crop-check",
                    }
                ],
            }
        ],
        "meter": {
            "hypotheses": ["Roman engineers", "An older, lost civilization"],
            "start": [50, 50],
        },
    }


def write_casefile(ep_dir: Path, data: dict | None = None) -> Path:
    path = ep_dir / "casefile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data or casefile()), encoding="utf-8")
    return path


PAPER = {"request_id": REQ, "slug": "the-megaliths"}


def write_media(ep_dir: Path) -> Path:
    """media/stone_person.jpg as a real 400x300 JPEG (the marker crop check reads it)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (200, 190, 170))
    ImageDraw.Draw(img).rectangle([40, 150, 80, 240], fill=(40, 40, 40))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    path = ep_dir / "media" / "stone_person.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
    return path


def accept_markers(ep_dir: Path, data: dict | None = None, verdict: str = "hits") -> None:
    """Export the marker crop checks of the case file and accept `verdict` for each."""
    from pipeline.studio import handoff, markers
    from pipeline.studio.casefile import from_dict

    cf = from_dict(data or casefile())
    markers.export_markers(ep_dir, cf)
    rows = handoff.read_jsonl(ep_dir / markers.CHECK_DIR / handoff.TASKS_FILE)
    handoff.write_jsonl(
        ep_dir / markers.CHECK_DIR / handoff.VERDICTS_FILE,
        [
            {
                "task_id": r["task_id"],
                "prompt_sha256": r["prompt_sha256"],
                "verdict": verdict,
                "explanation": "one person, inside the box",
                "answered_by": "claude-opus-5-5 (marker check agent)",
            }
            for r in rows
        ],
    )
    markers.import_markers(ep_dir)


def write_paper_workspace(
    assets: Path, evidence_ids: tuple[str, ...] = ("ev-01",), slug: str = "the-megaliths"
) -> Path:
    """<assets>/papers/<REQ>/: the published paper's evidence ids and its published slug."""
    root = assets / "papers" / REQ
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence.json").write_text(json.dumps([{"id": i} for i in evidence_ids]))
    (root / "publish_outcome.json").write_text(
        json.dumps({"apply": {"ok": True, "slug": slug}, "apply_exit_code": 0})
    )
    return root


def ready_workspace(ep_dir: Path) -> None:
    """Case file, its media, accepted marker checks and the paper workspace next to it."""
    write_casefile(ep_dir)
    write_media(ep_dir)
    accept_markers(ep_dir)
    write_paper_workspace(ep_dir.parent.parent)


def mutated(**changes) -> dict:
    data = copy.deepcopy(casefile())
    for dotted, value in changes.items():
        target = data
        keys = dotted.split("__")
        for k in keys[:-1]:
            target = target[int(k)] if k.isdigit() else target[k]
        last = keys[-1]
        target[int(last) if last.isdigit() else last] = value
    return data

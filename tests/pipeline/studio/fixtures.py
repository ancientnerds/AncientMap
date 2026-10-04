"""Builders for studio tests: a small version-1 dossier and a house-format draft.

Everything is built in tmp_path; no test reads video-assets/ or the network.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.studio import handoff
from pipeline.studio.paper.workspace import PaperWorkspace, parse_dossier, write_json

REQ = "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
S1 = "aaaaaaaaaaa1"  # DAI report, tier 1, full text
S2 = "bbbbbbbbbbb2"  # Wikipedia, tier 2, full text
S3 = "ccccccccccc3"  # abstract only
S4 = "ddddddddddd4"  # TDM-reserved, no body
S5 = "e5e5e5e5e5e5"  # behind an angle finding that shares S1: citable, full text
S6 = "f6f6f6f6f6f6"  # in the registry only: not citable, no text

S1_TEXT = (
    "Excavation report. The Stone of the Pregnant Woman weighs about 1000 tons. "
    "The block still lies in the Baalbek quarry. Jeanine Abdul Massih led the 2014 excavation. "
    "The block was quarried in the Roman period. The podium blocks and the quarry blocks "
    "share the same stone. It is likely that Roman engineers moved the blocks."
)
S2_TEXT = (
    "Baalbek is a city in the Beqaa Valley. The temple of Jupiter stands on a podium of "
    "800 tons blocks. Some estimates put the 2014 block at 1650 tons."
)
S3_TEXT = "Abstract. A survey of Levantine quarries."
S5_TEXT = "Geological survey. The quarry stone of Baalbek is a local limestone."

FILLER_SENTENCE = (
    "the block rests where the workers left it and the stone still shows the marks of the "
    "tools that cut it from the hill"
)


def dossier_dict() -> dict:
    return {
        "version": 1,
        "texts_mode": "cited",
        "request": {
            "id": REQ,
            "question": "How were the Baalbek megaliths moved?",
            "status": "researched",
            "is_batch": True,
            "user_id": "442000112756064260",
            "created_at": "2026-09-20T10:00:00+00:00",
            "completed_at": "2026-09-21T00:00:00+00:00",
        },
        "manifest": {
            "version": 1,
            "request_id": REQ,
            "question": "How were the Baalbek megaliths moved?",
            "created_at": "2026-09-21T00:00:00+00:00",
            "angle_ids": ["a1", "a2"],
            "counts": {
                "angles": 2,
                "findings": 3,
                "sources": 6,
                "final_claims": 2,
                "revised_claims": 1,
                "speculative_claims": 1,
                "images": 2,
            },
            "kinds": [
                "moderated",
                "synthesis",
                "debate",
                "angle_findings",
                "specialist_analyses",
                "citation_registry",
                "image_candidate_pool",
            ],
            "archive": {
                "cited_sources": 4,
                "full_text": 2,
                "abstract_only": 1,
                "missing": 0,
                "tdm_reserved": 1,
                "failures": [],
                "duration_s": 0.0,
                "timed_out": False,
            },
            "research": {"llm_calls": 300, "total_tokens": 9000000, "duration_s": 36000},
        },
        "moderated": {
            "final_claims": [
                {
                    "claim": "The Stone of the Pregnant Woman weighs about 1000 tons.",
                    "confidence": "high",
                    "source_ids": [S1],
                    "notes": "DAI survey",
                },
                {
                    "claim": "The podium blocks weigh about 800 tons.",
                    "confidence": "medium",
                    "source_ids": [S2],
                    "notes": "",
                },
            ],
            "revised_claims": [
                {
                    "original": "The 2014 block weighs 1650 tons.",
                    "revised": "Estimates for the 2014 block differ.",
                    "reason": "sources differ",
                    "source_ids": [S1, S2, S4],
                }
            ],
            "speculative_claims": [
                {
                    "claim": "An older civilization cut the blocks.",
                    "confidence": "low",
                    "source_ids": [S3],
                    "notes": "",
                    "what_would_strengthen": "a pre-Roman tool mark date",
                }
            ],
            "dropped_claims": [],
        },
        "synthesis": {
            "synthesis": {
                "consensus_claims": [
                    {
                        "claim": "The quarry blocks are Roman.",
                        "confidence": "high",
                        "source_ids": [S1],
                        "supporting_specialists": ["archaeologist"],
                    }
                ],
                "contested_claims": [
                    {
                        "claim": "The 2014 block is the heaviest.",
                        "for": {"evidence": "DAI weight estimate", "specialists": ["engineer"]},
                        "against": {
                            "evidence": "Wikipedia gives a higher figure",
                            "specialists": ["historian"],
                        },
                        "source_ids": [S1, S2],
                    }
                ],
                "unique_insights": [],
                "open_questions": ["How were the blocks lifted onto the podium?"],
                "convergent_findings": [
                    {
                        "pattern": "Quarry and podium stone match.",
                        "significance": "the podium was built from this quarry",
                        "angles_involved": [
                            {
                                "angle_id": 1,
                                "angle_topic": "Quarry",
                                "finding": "The quarry stone is a local limestone.",
                                "source_ids": [S5],
                            },
                            {
                                "angle_id": 2,
                                "angle_topic": "Podium",
                                "finding": "The podium blocks are of the same limestone.",
                                "source_ids": [S2],
                            },
                        ],
                    }
                ],
                "contradictions": [
                    {
                        "description": "the weight of the 2014 block",
                        "side_a": {"angle_id": 1, "angle_topic": "Quarry", "position": "1000 tons"},
                        "side_b": {"angle_id": 2, "angle_topic": "Podium", "position": "1650 tons"},
                    }
                ],
                "cross_angle_gaps": [
                    {
                        "topic": "lifting",
                        "why_important": "the podium is higher than the quarry floor",
                        "suggested_queries": ["Baalbek podium lifting"],
                    }
                ],
            },
            "cross_angle_connections": [
                {
                    "description": "same stone",
                    "from_angle": {
                        "angle_id": 1,
                        "finding": "The quarry stone is a local limestone.",
                        "source_ids": [S5],
                    },
                    "to_angle": {
                        "angle_id": 2,
                        "finding": "The podium blocks are of the same limestone.",
                        "source_ids": [S2],
                    },
                }
            ],
        },
        "debate": {
            "rounds": 2,
            "challenges": [
                {
                    "target_claim": "The 2014 block weighs 1650 tons.",
                    "target_specialist": "engineer",
                    "suggestion_type": "revise",
                    "suggestion": "Give the range of estimates.",
                    "evidence": "sources differ",
                    "source_ids": [S1, S2],
                    "challenger_id": "historian",
                }
            ],
            "defenses": [
                {
                    "suggestion_id": 0,
                    "response": "accept",
                    "argument": "Range adopted.",
                    "additional_evidence": "",
                    "source_ids": [],
                    "defender_id": "engineer",
                }
            ],
        },
        "angles": [
            {
                "id": "a1",
                "topic": "Quarry",
                "description": "the quarry",
                "findings": [
                    {
                        "claim": "The quarry stone is a local limestone.",
                        "evidence": "geological survey",
                        "source_ids": [S1, S5],
                        "confidence": "high",
                        "specialist_id": "geologist",
                    },
                    {
                        "claim": "Quarry workers lived nearby.",
                        "evidence": "a blog post",
                        "source_ids": [S6],
                        "confidence": "low",
                        "specialist_id": "historian",
                    },
                ],
            },
            {
                "id": "a2",
                "topic": "Podium",
                "description": "the podium",
                "findings": [
                    {
                        "claim": "The podium blocks weigh about 800 tons.",
                        "evidence": "encyclopedia",
                        "source_ids": [S2],
                        "confidence": "medium",
                        "specialist_id": "engineer",
                    }
                ],
            },
        ],
        "sources": [
            {
                "id": S1,
                "url": "https://www.dainst.org/baalbek-report",
                "title": "Baalbek quarry excavation report",
                "domain": "dainst.org",
                "reliability_tier": 1,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "2015",
                "license": "",
                "source_api": "web",
                "archive": {
                    "content_type": "text/html",
                    "text_chars": len(S1_TEXT),
                    "fetched_at": "2026-09-20T11:00:00+00:00",
                    "tdm_opt_out": False,
                },
            },
            {
                "id": S2,
                "url": "https://en.wikipedia.org/wiki/Baalbek",
                "title": "Baalbek - Wikipedia",
                "domain": "en.wikipedia.org",
                "reliability_tier": 2,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "",
                "license": "CC BY-SA 4.0",
                "source_api": "wikipedia",
                "archive": {
                    "content_type": "text/html",
                    "text_chars": len(S2_TEXT),
                    "fetched_at": "2026-09-20T11:05:00+00:00",
                    "tdm_opt_out": False,
                },
            },
            {
                "id": S3,
                "url": "https://example.org/levant-quarries",
                "title": "Levantine quarries",
                "domain": "example.org",
                "reliability_tier": 3,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "",
                "license": "",
                "source_api": "openalex",
                "archive": {
                    "content_type": "adapter/snippet",
                    "text_chars": len(S3_TEXT),
                    "fetched_at": "2026-09-20T11:06:00+00:00",
                    "tdm_opt_out": False,
                },
            },
            {
                "id": S4,
                "url": "https://publisher.example/paywalled",
                "title": "Paywalled monograph",
                "domain": "publisher.example",
                "reliability_tier": 1,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "",
                "license": "",
                "source_api": "crossref",
                "archive": {
                    "content_type": "text/html",
                    "text_chars": 0,
                    "fetched_at": "2026-09-20T11:07:00+00:00",
                    "tdm_opt_out": True,
                },
            },
            {
                "id": S5,
                "url": "https://example.org/baalbek-geology",
                "title": "Baalbek geology",
                "domain": "example.org",
                "reliability_tier": 2,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "2019",
                "license": "",
                "source_api": "web",
                "archive": {
                    "content_type": "text/html",
                    "text_chars": len(S5_TEXT),
                    "fetched_at": "2026-09-20T11:08:00+00:00",
                    "tdm_opt_out": False,
                },
            },
            {
                "id": S6,
                "url": "https://blog.example/baalbek",
                "title": "A Baalbek blog",
                "domain": "blog.example",
                "reliability_tier": 3,
                "doi": "",
                "authors": [],
                "venue": "",
                "date": "",
                "license": "",
                "source_api": "web",
                "archive": None,
            },
        ],
        "texts": {S1: S1_TEXT, S2: S2_TEXT, S3: S3_TEXT, S5: S5_TEXT},
        "images": {
            "a1": [
                {
                    "url": "https://commons.wikimedia.org/wiki/File:Baalbek_stone.jpg",
                    "source": "wikimedia",
                    "title": "Stone of the Pregnant Woman in the Baalbek quarry",
                    "description": "The megalith in the quarry",
                    "artist": "Jane Doe",
                    "license": "CC BY-SA 4.0",
                    "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
                    "thumbnail_url": "https://upload.wikimedia.org/thumb/Baalbek_stone.jpg",
                    "metadata": {"width": 1280, "height": 800},
                },
                {
                    "url": "https://commons.wikimedia.org/wiki/File:Cat.jpg",
                    "source": "wikimedia",
                    "title": "A cat",
                    "description": "",
                    "artist": "",
                    "license": "CC0",
                    "license_url": "",
                    "thumbnail_url": "https://upload.wikimedia.org/thumb/Cat.jpg",
                    "metadata": {},
                },
            ]
        },
    }


def legacy_dossier_dict() -> dict:
    """The export of a run that predates the DossierHandler (e.g. 95fa3798): stream A's
    legacy manifest (no created_at, research duration unknown, the old paper_final kind)."""
    data = dossier_dict()
    data["manifest"] = {
        "version": 1,
        "legacy": True,
        "request_id": REQ,
        "question": data["request"]["question"],
        "created_at": None,
        "angle_ids": ["a1", "a2"],
        "counts": data["manifest"]["counts"],
        "kinds": [
            "angle_findings",
            "citation_registry",
            "debate",
            "moderated",
            "paper_final",
            "synthesis",
        ],
        "archive": {
            "cited_sources": 4,
            "full_text": 2,
            "abstract_only": 1,
            "missing": 0,
            "tdm_reserved": 1,
            "failures": [],
            "duration_s": 0.0,
            "timed_out": False,
        },
        "research": {"llm_calls": 300, "total_tokens": 9000000, "duration_s": None},
    }
    return data


def dossier_gz_bytes(data: dict | None = None) -> bytes:
    """The export's encoding (stream A's C3): UTF-8 JSON, gzip with mtime 0."""
    payload = json.dumps(data or dossier_dict(), ensure_ascii=False).encode("utf-8")
    return gzip.compress(payload, mtime=0)


def filler_paragraph(source_id: str = S1, sentences: int = 5) -> str:
    body = ". ".join([FILLER_SENTENCE] * sentences)
    return f"{body} [S:{source_id}]."


HOOK = (
    "In 2014 an excavation team measured a block that still lies in the Baalbek quarry "
    "[S:aaaaaaaaaaa1]."
)
SECTIONS = [
    (
        "How Heavy Is Heavy",
        [
            "The Stone of the Pregnant Woman weighs about 1000 tons [S:aaaaaaaaaaa1]. "
            "It still lies in the Baalbek quarry [S:aaaaaaaaaaa1].",
            "The temple of Jupiter stands on a podium of 800 tons blocks [S:bbbbbbbbbbb2]. "
            "Some estimates put the 2014 block at 1650 tons [S:bbbbbbbbbbb2].",
        ],
    ),
    (
        "Who Cut the Blocks",
        [
            "Jeanine Abdul Massih led the 2014 excavation [S:aaaaaaaaaaa1]. "
            "The block was quarried in the Roman period [S:aaaaaaaaaaa1].",
        ],
    ),
    (
        "How They Moved It",
        [
            "The quarry stone of Baalbek is a local limestone, and the temple of Jupiter "
            "stands on a podium of 800 tons blocks [S:e5e5e5e5e5e5] [S:bbbbbbbbbbb2].",
        ],
    ),
    (
        "Connecting the Dots",
        [
            "The podium blocks and the quarry blocks share the same stone "
            "[S:aaaaaaaaaaa1] [S:bbbbbbbbbbb2].",
        ],
    ),
    (
        "The Other Side",
        [
            "Baalbek is a city in the Beqaa Valley, and some estimates put the 2014 block "
            "at 1650 tons [S:bbbbbbbbbbb2].",
            filler_paragraph(S2),
        ],
    ),
    (
        "What We Actually Know",
        ["It is likely that Roman engineers moved the blocks [S:aaaaaaaaaaa1]."],
    ),
]


def build_draft(filler: int = 9) -> str:
    """A house-format draft: the hook (two paragraphs, no heading), three investigation
    sections and the three fixed ones; filler=9 gives about 5,600 prose words.

    Three investigation sections is the current floor (`gates.INVESTIGATIONS`).
    Every section's lead sentence is distinct, so an image opportunity can anchor
    to exactly one of them — an anchor that matches several paragraphs is refused.
    """
    parts: list[str] = [HOOK, filler_paragraph()]
    for heading, leads in SECTIONS:
        parts.append(f"## {heading}")
        parts.extend(leads)
        parts.extend(filler_paragraph() for _ in range(filler))
    return "\n\n".join(parts) + "\n"


META = {
    "title": "The Megaliths of the Baalbek Quarry",
    "card_description": "The paper finds that Roman engineers quarried and moved the "
    "Baalbek megaliths, and that weight estimates for the largest block differ.",
}

EVIDENCE = [
    {
        "id": "ev-01",
        "anchor_text": "The Stone of the Pregnant Woman weighs about 1000 tons",
        "claim": "The Stone of the Pregnant Woman weighs about 1000 tons.",
        "source_ids": [S1],
        "quote": "The Stone of the Pregnant Woman weighs about 1000 tons.",
        "quote_source_id": S1,
        "verdict": "supported",
    },
    {
        "id": "ev-02",
        "anchor_text": "The temple of Jupiter stands on a podium of 800 tons blocks",
        "claim": "The podium blocks weigh about 800 tons.",
        "source_ids": [S2],
        "quote": "The temple of Jupiter stands on a podium of 800 tons blocks.",
        "quote_source_id": S2,
        "verdict": "supported",
    },
]


def make_workspace(
    root: Path, *, draft: str | None = None, dossier: dict | None = None
) -> PaperWorkspace:
    """A pulled workspace with Claude's three files written."""
    ws = PaperWorkspace(root / "papers" / REQ, REQ)
    ws.root.mkdir(parents=True)
    ws.dossier_gz.write_bytes(dossier_gz_bytes(dossier))
    ws.texts_dir.mkdir()
    for sid, text in parse_dossier(ws.dossier_gz.read_bytes()).texts.items():
        ws.text_path(sid).write_text(text, encoding="utf-8")
    ws.draft.write_text(draft if draft is not None else build_draft(), encoding="utf-8")
    write_json(ws.meta, META)
    write_json(ws.evidence, EVIDENCE)
    return ws


# --- images -------------------------------------------------------------------------------

OPS = [
    {
        "id": "op-01",
        "anchor_text": "The Stone of the Pregnant Woman weighs about 1000 tons",
        "subject": "The Stone of the Pregnant Woman lying in the quarry",
        "queries": ["Stone of the Pregnant Woman"],
    }
]

# One opportunity per section: the floor the images gate enforces (owner decision
# 2026-10-04, at least one image per section). Each query gets its own picture, so
# the per-file content dedup does not reject the set.
OPS_ONE_PER_SECTION = [
    {
        "id": "op-01",
        "anchor_text": "The Stone of the Pregnant Woman weighs about 1000 tons",
        "subject": "The Stone of the Pregnant Woman lying in the quarry",
        "queries": ["Stone of the Pregnant Woman"],
    },
    {
        "id": "op-02",
        "anchor_text": "It is likely that Roman engineers moved the blocks",
        "subject": "Roman engineers moving the Baalbek blocks",
        "queries": ["Roman engineers Baalbek"],
    },
    {
        "id": "op-03",
        "anchor_text": "Jeanine Abdul Massih led the 2014 excavation",
        "subject": "The 2014 excavation in the Baalbek quarry",
        "queries": ["Baalbek excavation 2014"],
    },
    {
        "id": "op-04",
        "anchor_text": "The quarry stone of Baalbek is a local limestone",
        "subject": "The limestone of the Baalbek quarry",
        "queries": ["Baalbek limestone quarry"],
    },
    {
        "id": "op-05",
        "anchor_text": "The podium blocks and the quarry blocks share the same stone",
        "subject": "Baalbek podium and quarry blocks of the same stone",
        "queries": ["Baalbek podium blocks"],
    },
    {
        "id": "op-06",
        "anchor_text": "Baalbek is a city in the Beqaa Valley",
        "subject": "The Beqaa Valley and the city of Baalbek",
        "queries": ["Baalbek Beqaa Valley"],
    },
]


def png(seed: int, width: int = 900, height: int = 600) -> bytes:
    """A distinct picture per seed (different dhash), `width` x `height` pixels."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i in range(8):
        x = (seed * 97 + i * 131) % (width - 100)
        y = (seed * 53 + i * 71) % (height - 100)
        colour = (i * 30 % 255, seed * 40 % 255, 90)
        draw.rectangle([x, y, x + 60 + seed * 7 % 40, y + 80], fill=colour)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


IMAGE_BYTES = {
    "https://commons.wikimedia.org/wiki/File:Baalbek_stone.jpg": png(1),
    "https://example.org/found-1": png(2),
    "https://example.org/found-dup": png(1),
    "https://example.org/tiny": png(3, width=200, height=150),
}


async def fake_search(query: str) -> list[ImageCandidate]:
    assert query == "Stone of the Pregnant Woman"
    urls = [
        "https://example.org/found-1",
        "https://example.org/found-dup",
        "https://example.org/tiny",
    ]
    found = [
        ImageCandidate(
            url=u, source="europeana", title=f"Stone {i}", license="CC BY 4.0", artist="X"
        )
        for i, u in enumerate(urls)
    ]
    cat = ImageCandidate(
        url="https://example.org/cat", source="europeana", title="A cat", license="CC0"
    )
    return [*found, cat]


# One picture per query of OPS_ONE_PER_SECTION, each with its own dhash.
_SECTION_IMAGE_SEEDS = {
    "Stone of the Pregnant Woman": 11,
    "Roman engineers Baalbek": 12,
    "Baalbek excavation 2014": 13,
    "Baalbek limestone quarry": 14,
    "Baalbek podium blocks": 15,
    "Baalbek Beqaa Valley": 16,
}
IMAGE_BYTES = {
    "https://commons.wikimedia.org/wiki/File:Baalbek_stone.jpg": png(1),
    "https://example.org/found-1": png(2),
    "https://example.org/found-dup": png(1),
    "https://example.org/tiny": png(3, width=200, height=150),
    **{f"https://example.org/section-{i}": png(seed) for i, seed in enumerate(
        _SECTION_IMAGE_SEEDS.values(), start=1
    )},
}


async def fake_search_per_section(query: str) -> list[ImageCandidate]:
    """One safe, distinct picture per query, so every section of the draft can
    carry its own image without the per-file content dedup rejecting the set."""
    assert query in _SECTION_IMAGE_SEEDS, f"unexpected query {query!r}"
    index = list(_SECTION_IMAGE_SEEDS).index(query) + 1
    return [
        ImageCandidate(
            url=f"https://example.org/section-{index}",
            source="wikimedia",
            title=f"{query} (photograph)",
            license="CC BY 4.0",
            artist="X",
        )
    ]


async def fake_download(cand: ImageCandidate, out_path: Path) -> bool:
    out_path.write_bytes(IMAGE_BYTES[cand.url])
    return True


QUOTES = {
    S1: "The block still lies in the Baalbek quarry.",
    S2: "Baalbek is a city in the Beqaa Valley.",
    S5: "The quarry stone of Baalbek is a local limestone.",
}


def claim_answers(rows: list[dict], verdict: str = "supported") -> list[dict]:
    out = []
    for r in rows:
        supported = verdict == "supported" and r["kind"] != "coherence"
        qsid = r["cited"][0]["source_id"] if supported else ""
        out.append(
            {
                "task_id": r["task_id"],
                "prompt_sha256": r["prompt_sha256"],
                "verdict": verdict,
                "quote": QUOTES[qsid] if supported else "",
                "quote_source_id": qsid,
                "explanation": "",
                "fix_suggestion": "",
                "answered_by": "claude-opus-5-5 (Claude Code agent)",
                "skeptic_by": "claude-opus-5-5 (skeptic agent)" if supported else "",
            }
        )
    return out


def image_answers(rows: list[dict], verdicts: list[str]) -> list[dict]:
    return [
        {
            "task_id": r["task_id"],
            "prompt_sha256": r["prompt_sha256"],
            "verdict": v,
            "depicts": "a megalith in a quarry",
            "subject_box": [0.1, 0.1, 0.5, 0.5],
            "caption": "The Stone of the Pregnant Woman in the Baalbek quarry"
            if v in ("meaningful", "weak")
            else "",
            "answered_by": "claude-opus-5-5 (Claude Code agent)",
        }
        for r, v in zip(rows, verdicts, strict=True)
    ]


def complete_workspace(root: Path, *, dossier: dict | None = None) -> PaperWorkspace:
    """A workspace that passes every gate: claims all supported, and one checked
    image in every section (the floor `gates.IMAGES_MIN_PER_SECTION` enforces)."""
    from pipeline.studio.paper import claims, images

    ws = make_workspace(root, dossier=dossier)
    write_json(ws.images_dir / "opportunities.json", OPS_ONE_PER_SECTION)
    images.export_images(ws, search=fake_search_per_section, download=fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", image_answers(rows, ["meaningful"] * len(rows))
    )
    images.import_images(ws)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    handoff.write_jsonl(ws.claims_dir / "verdicts.jsonl", claim_answers(rows))
    claims.import_claims(ws)
    return ws

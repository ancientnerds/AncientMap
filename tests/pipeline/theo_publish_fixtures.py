"""Shared fixtures for the Theo publish tests: one paper that passes every gate.

REPORT was checked against validate_paper_artifact (passed, no issues),
recompute_quality_passed (True with QUALITY) and, with TITLE, against the
paper page's own anchor resolution when this plan was written.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from tests.fake_sql import FakeResult, RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
OTHER_REQ = "99999999-8888-7777-6666-555555555555"
IMG_NAME = "p1_trilithon.jpg"
IMG = f"/data/research-images/{REQ}/{IMG_NAME}"
SOURCE_A = "a1b2c3d4e5f6"
SOURCE_B = "0f1e2d3c4b5a"
TITLE = "The Baalbek Trilithon"

REPORT = f"""# The Baalbek Trilithon

In 2014 a team from the German Archaeological Institute measured a third monolith in the Baalbek quarry [1].

## The Quarry Blocks

The Stone of the Pregnant Woman weighs roughly 1,000 tonnes according to the institute survey [1]. A second block nearby is heavier still [2].

![Quarry block with a person for scale]({IMG})

*Quarry block with a person for scale*
[Source](https://commons.wikimedia.org/wiki/File:Baalbek.jpg)

## Connecting the Dots

Both blocks were cut from the same limestone bed that supplied the temple podium [2].

## The Other Side

Roman engineers moved blocks of this size with capstans and ramps, as the survey notes [1].

## What We Actually Know

The quarry dates to the Roman period, which the excavation layers confirm [2].

## References

[1] Baalbek quarry survey — https://a.example/survey (accessed 2026-09-01) [Academic]
[2] Limestone beds of the Beqaa — https://a.example/beds (accessed 2026-09-01)
"""

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}

QUALITY = {
    "score": 92,
    "badge": "Claim-checked",
    "passed": True,
    "metrics": {"citation_coverage": 15, "reference_integrity": 10},
    "meta": {"word_count": 120},
    "audit_gate_failures": {
        "audit_passed": True,
        "hallucination_final": 0,
        "high_contradictions": 0,
        "undefined_title_terms": 0,
    },
}

HERO = {
    "src": IMG,
    "web_path": IMG,
    "title": "Quarry block",
    "caption": "Quarry block with a person for scale",
    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Baalbek.jpg",
    "source_name": "Wikimedia Commons",
    "rationale": "Shows the block with a person for scale",
}

EVIDENCE = [
    {
        "id": "ev-01",
        "anchor_text": "The Stone of the Pregnant Woman weighs roughly",
        "claim": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
        "source_ids": [SOURCE_A],
        "quote": "weighs about 1,000 tonnes",
        "quote_source_id": SOURCE_A,
        "verdict": "supported",
    },
    {
        "id": "ev-02",
        "anchor_text": "The quarry dates to the Roman period",
        "claim": "The quarry is Roman.",
        "source_ids": [SOURCE_B],
        "quote": "Roman period",
        "quote_source_id": SOURCE_B,
        "verdict": "supported",
    },
]

DOSSIER_SUMMARY = {
    "artifact_id": 8,
    "version": 1,
    "created_at": "2026-09-28T09:00:00+00:00",
    "counts": {
        "angles": 2,
        "findings": 10,
        "sources": 40,
        "final_claims": 4,
        "revised_claims": 0,
        "speculative_claims": 1,
        "images": 12,
    },
    "archive": {
        "cited_sources": 6,
        "full_text": 5,
        "abstract_only": 1,
        "missing": 0,
        "tdm_reserved": 0,
    },
}


def images_tree(tmp_path: Path, *names: str, request_id: str = REQ) -> tuple[Path, Path]:
    """A served-data tree with the paper's pictures in it, as the site has them.

    Returns `(images_root, served_root)`: `images_root` is the directory
    `RESEARCH_IMAGES_DIR` names, `served_root` the one above it that nginx serves
    as `/data/` and that a web path in a paper resolves against
    (`theo_publishing.check_pictures`). In production the two are one tree, so a
    test that puts a file in one without the other gets `not_served` out of the
    other - which is the point of the rule.
    """
    served = tmp_path / "data"
    images_root = served / "research-images"
    (images_root / request_id).mkdir(parents=True)
    for name in names:
        (images_root / request_id / name).write_bytes(b"jpeg")
    return images_root, served


def make_result(**overrides) -> dict:
    """A publish-bundle `result` that passes every gate."""
    result = {
        "title": TITLE,
        "card_description": "The quarry blocks of Baalbek are Roman work, moved with capstans and ramps.",
        "report": REPORT,
        "published_report": REPORT,
        "hero_image": copy.deepcopy(HERO),
        "published_hero_image": copy.deepcopy(HERO),
        "probative_images": [
            {
                "title": "Quarry block",
                "web_path": IMG,
                "verified": True,
                "license": "CC BY-SA 4.0",
                "source_url": "https://commons.wikimedia.org/wiki/File:Baalbek.jpg",
            }
        ],
        "published_block_ids": [],
        "quality_score": copy.deepcopy(QUALITY),
        "evidence": copy.deepcopy(EVIDENCE),
        "corrections": [],
    }
    result.update(overrides)
    return result


def capture_notices(monkeypatch) -> dict[str, list]:
    """Stub the owner notice's two senders and record what they got.

    The thinking_log event (always written) and the Discord webhook (unset by
    owner decision 5, so the stub returns False like the real sender does).
    Each publish test module wraps this in its own autouse `notices` fixture.
    """
    calls: dict[str, list] = {"thinking": [], "discord": []}
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details=None: calls["thinking"].append((kind, summary, details)),
    )
    monkeypatch.setattr(
        "pipeline.utils.notify.send_discord_webhook",
        lambda payload: calls["discord"].append(payload) or False,
    )
    return calls


def research_row(**overrides) -> SimpleNamespace:
    """The research_requests row as theo_publishing reads it (researched, not public)."""
    values = {
        "id": REQ,
        "status": "researched",
        "is_public": False,
        "slug": None,
        "question": "Who cut the Baalbek monoliths?",
        "user_id": "442000112756064260",
        "published_by": None,
        "published_at": None,
        "result_json": json.dumps({"dossier": DOSSIER_SUMMARY, "title": None}),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PublishSession(RecordingSession):
    """The research_requests rows that the publish writes change, as the database would.

    `row` is the paper being written; `others` are further rows by id (the fresh
    Theo run whose dossier a full republish takes, C5 `dossier_request_id`).
    `journal` is the theo_paper_publications rows the paper already has (rule 7's
    idempotence lookup reads them); an INSERT appends one, as the database would,
    so a second identical write in the same session sees the first.
    """

    def __init__(
        self,
        row,
        *,
        others=(),
        slug_taken=False,
        update_rowcount=1,
        close_rowcount=1,
        tamper=False,
        journal=(),
    ):
        super().__init__()
        self.row = row
        self.others = {other.id: other for other in others}
        self.slug_taken = slug_taken
        self.update_rowcount = update_rowcount
        self.close_rowcount = close_rowcount
        self.tamper = tamper
        self.journal = list(journal)
        self.written = None
        self.closed = None
        self.slug_after = row.slug
        self.published_by_after = row.published_by

    def _newest_journal(self, request_id: str):
        """The row _ALREADY_APPLIED_SQL's MAX(id) subquery returns, as the database would."""
        rows = [entry for entry in self.journal if entry.request_id == request_id]
        return max(rows, key=lambda entry: entry.id) if rows else None

    def execute(self, stmt, params=None):
        super().execute(stmt, params)
        sql = stmt.text
        if "published_by, published_at, result_json" in sql:
            if params["id"] == self.row.id:
                return FakeResult([self.row])
            return FakeResult([self.others[params["id"]]] if params["id"] in self.others else [])
        if "SELECT 1 FROM research_requests WHERE slug" in sql:
            return FakeResult([object()] if self.slug_taken else [])
        if "SET status = 'cancelled'" in sql:
            self.closed = params
            return FakeResult([], rowcount=self.close_rowcount)
        if "MAX(id)" in sql:
            newest = self._newest_journal(params["request_id"])
            if (
                newest is not None
                and newest.action == params["action"]
                and newest.bundle_sha256 == params["bundle_sha256"]
            ):
                return FakeResult([newest])
            return FakeResult([])
        if sql.lstrip().startswith("UPDATE research_requests"):
            self.written = params["result"]
            self.slug_after = params.get("slug", self.row.slug)
            self.published_by_after = params.get("author", self.row.published_by)
            # The row carries the new payload, as the database would: a second
            # write in the same session reads what the first one stored.
            self.row.result_json = params["result"]
            if "is_public = TRUE" in sql:
                self.row.status, self.row.is_public = "completed", True
                self.row.slug, self.row.published_by = self.slug_after, self.published_by_after
            return FakeResult([], rowcount=self.update_rowcount)
        if "INSERT INTO theo_paper_publications" in sql:
            journal_id = 42 + len(self.journal)
            self.journal.append(
                SimpleNamespace(
                    id=journal_id,
                    request_id=params["request_id"],
                    action=params["action"],
                    slug=params["slug"],
                    bundle_sha256=params["bundle_sha256"],
                    gates=json.loads(params["gates"]),
                    side_effects=None,
                )
            )
            return FakeResult([(journal_id,)])
        if "SELECT status, is_public, slug, published_by, result_json" in sql:
            written = json.dumps({"tampered": True}) if self.tamper else self.written
            return FakeResult(
                [
                    SimpleNamespace(
                        status="completed",
                        is_public=True,
                        slug=self.slug_after,
                        published_by=self.published_by_after,
                        result_json=written,
                    )
                ]
            )
        return FakeResult([])


def journal_entry(journal_id: int, *, action: str, bundle_sha256: str, request_id: str = REQ, **kw):
    """A theo_paper_publications row as the idempotence lookup reads it."""
    values = {
        "id": journal_id,
        "request_id": request_id,
        "action": action,
        "slug": "the-baalbek-trilithon",
        "bundle_sha256": bundle_sha256,
        "gates": {"status": {"passed": True, "issues": []}},
        "side_effects": {"indexnow": {"ok": True}},
    }
    values.update(kw)
    return SimpleNamespace(**values)

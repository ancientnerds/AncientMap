"""Shared fixtures of the identity package's question and write tests (D13, D20, D23).

DB-less and offline: every cited page is stored with `quotes.store_page` as a fetch would have kept
it, every title resolution is a dict, every answer is written through `opus_handoff.write_answer`
under the role of its stage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _root in (
    str(REPO),
    str(REPO / "scripts" / "remediation"),
    str(REPO / "output" / "remediation" / "tools"),
):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from identity import rounds as R  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

NOW = "2026-10-09T02:00:00+00:00"
ENT = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
WP = "https://en.wikipedia.org/wiki/"


def store(
    pages: Path, url: str, body: bytes, *, content_type: str = "text/html", status: int = 200
) -> None:
    Q.store_page(
        pages,
        url,
        status=status,
        final_url=url,
        content_type=content_type,
        body=body,
        error="",
        fetched_at=NOW,
    )


def html(*sentences: str) -> bytes:
    return ("<html><body>" + "".join(f"<p>{s}</p>" for s in sentences) + "</body></html>").encode()


def entity(
    qid: str,
    label: str,
    lat: float | None,
    lon: float | None,
    aliases: dict[str, list[str]] | None = None,
    description: str | None = None,
) -> bytes:
    claims = {}
    if lat is not None:
        value = {"latitude": lat, "longitude": lon, "precision": 0.0001, "globe": "Q2"}
        claims["P625"] = [{"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}]
    body = {
        "entities": {
            qid: {
                "id": qid,
                "labels": {"en": {"language": "en", "value": label}},
                "descriptions": {"en": {"language": "en", "value": description}}
                if description
                else {},
                "aliases": {
                    lang: [{"language": lang, "value": v} for v in values]
                    for lang, values in (aliases or {}).items()
                },
                "claims": claims,
            }
        }
    }
    return json.dumps(body).encode()


def resolution(qid: str | None, lat: float | None = None, lon: float | None = None, **over: Any):
    base = {
        "canonical_title": "x",
        "qid": qid,
        "lat": lat,
        "lon": lon,
        "disambiguation": False,
        "redirected": False,
    }
    base.update(over)
    return base


class FakeClient:
    """No page is fetched in the tests: every cited page is stored beforehand."""

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def get(self, url: str) -> Any:
        raise AssertionError(f"no page should be fetched: {url}")


def resolver_of(titles: dict[str, dict[str, Any]]):
    def resolver(wanted: list[str], client: Any) -> dict[str, dict[str, Any]]:
        return {t: titles[t] for t in wanted}

    return resolver


def answer_all(
    root: Path, record: R.Round, spec: R.StageSpec, texts: dict[str, Any], *, now: str = NOW
) -> None:
    """Every question of the round answered under the stage's role, as `answer --role` records it."""
    for batch_id, sids in record.batches.items():
        for sid in sids:
            text = texts[sid] if isinstance(texts[sid], str) else json.dumps(texts[sid])
            OH.write_answer(
                root,
                batch_id=batch_id,
                stage=spec.stage,
                label=sid,
                text=text,
                answered_by=RO.answered_by(spec.role, batch_id),
                model=OH.ANSWER_MODELS[spec.model],
                now=lambda: now,
            )

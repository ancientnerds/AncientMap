"""Batch directories and a scripted model for the Track-B tests (phase 4, WB-B2 ... WB-B4).

Nothing here opens a socket or starts a process. The article texts are written for the tests in
the shape of a TextExtracts plain-text extract (a lead, `== Heading ==` lines, `c. 2500 BC`,
parentheses and comma insertions); no Wikipedia text is copied into the repository.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHASE_PARENT = REPO / "scripts" / "remediation"
if str(PHASE_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase4 import model4 as M  # noqa: E402

#: A lead of four sentences and two sections; sentence numbers are the split's own (W1 ... W12).
ARTICLE = (
    "The Stone Temple is a megalithic temple on the island of Gozo. "
    "The temple was built c. 2500 BC by a farming community, whose tombs lie nearby. "
    "In 1900, the site was cleared of rubble by the island's governor. "
    "It is probably the oldest temple on the island.\n"
    "\n\n== History ==\n\n"
    "The temple, which stood on a low ridge, was used for about a thousand years. "
    "A second shrine (the south shrine) was added later. "
    "Excavations in 1911 found pottery, figurines and animal bones. "
    "The finds are kept in the national museum.\n"
    "\n\n== References ==\n\n"
    "Smith, J. The Temples of Gozo, 1990.\n"
    "\n\n== Location ==\n\n"
    "The site lies 2 km south of the village – near the old road – on farmland. "
    "Visitors can reach it by bus. "
    "It is open on weekdays.\n"
)
ARTICLE_TITLE = "Stone Temple"
PERMALINK = "https://en.wikipedia.org/w/index.php?title=Stone_Temple&oldid=1234567"


def sid_of(text: str, sentence: str, source_id: str = "W") -> str:
    """The sid of `sentence` in the split of `text` (tests name sentences by their words)."""
    from phase4 import sentences as S

    for candidate in S.split_source(source_id, text):
        if S.sentence_text(text, candidate) == sentence:
            return candidate.sid
    raise AssertionError(f"not a sentence of the text: {sentence!r}")


def plan_site(
    site_id: str = "site-1",
    *,
    name: str = "Stone Temple",
    aliases: tuple[str, ...] = (),
    country: str | None = "Malta",
    description: str | None = "A stored description.",
    raw_data: dict | None = None,
    card: str | None = "A stored card.",
    flags: frozenset[M.SiteFlag] = frozenset(),
) -> M.PlanSite:
    return M.PlanSite(
        site_id=site_id,
        name=name,
        aliases=aliases,
        country=country,
        site_type="Temple",
        period_start=-2500,
        period_end=None,
        lat=36.05,
        lon=14.27,
        description=description,
        description_sha256=None if description is None else M.text_sha256(description),
        raw_data=raw_data,
        raw_data_sha256=None if raw_data is None else M.text_sha256(json.dumps(raw_data)),
        card=card,
        card_sha256=None if card is None else M.text_sha256(card),
        source_url=None,
        wikidata_qid="Q1",
        enwiki_title=name,
        in_snapshot=True,
        snapshot_description=None,
        flags=flags,
    )


def wiki_doc(
    source_id: str, text: str, *, title: str = ARTICLE_TITLE, host: str = "en.wikipedia.org"
) -> M.SourceDoc:
    permalink = f"https://{host}/w/index.php?title={title.replace(' ', '_')}&oldid=1234567"
    return M.SourceDoc(
        id=source_id,
        url=f"https://{host}/w/api.php?action=query&titles={title.replace(' ', '%20')}",
        permalink=permalink,
        title=title,
        pageid=77,
        revid=1234567,
        lastrevid=1234567,
        rev_timestamp="2026-09-01T10:00:00Z",
        retrieved_at="2026-09-23T08:00:00Z",
        sha256_raw=M.text_sha256("raw " + text),
        sha256_text=M.text_sha256(text),
        licence=M.Licence.CC_BY_SA_4,
        route=M.Route.ENWIKI_TITLE,
        subject_gate=None,
        tdm=None,
        final_url=None,
        truncated=None,
    )


def page_doc(
    source_id: str, text: str, *, url: str, title: str | None = "A page about the temple"
) -> M.SourceDoc:
    return M.SourceDoc(
        id=source_id,
        url=url,
        permalink=None,
        title=title,
        pageid=None,
        revid=None,
        lastrevid=None,
        rev_timestamp=None,
        retrieved_at="2026-09-23T08:00:00Z",
        sha256_raw=M.text_sha256("raw " + text),
        sha256_text=M.text_sha256(text),
        licence=M.Licence.RESTRICTED,
        route=M.Route.MINIMAX,
        subject_gate=None,
        tdm=M.Tdm(checked=True, reserved=False, signal=None),
        final_url=url,
        truncated=False,
    )


@dataclass
class SiteSetup:
    """One site of a test batch: its plan record, its lane and its stored sources."""

    site: M.PlanSite
    lane: M.Lane
    sources: dict[str, tuple[M.SourceDoc, str]] = field(default_factory=dict)


def w_site(site_id: str = "site-1", *, lane: M.Lane = M.Lane.W, **kw: object) -> SiteSetup:
    return SiteSetup(
        site=plan_site(site_id, **kw),  # type: ignore[arg-type]
        lane=lane,
        sources={"W": (wiki_doc("W", ARTICLE), ARTICLE)},
    )


def make_batch(
    root: Path, setups: Sequence[SiteSetup], *, run: str = "pilot", batch: str = "p4-0001"
) -> Path:
    """`runs/<run>/<batch>/` with input.json, lanes.jsonl and every source in the evidence store."""
    batch_dir = root / "runs" / run / batch
    batch_dir.mkdir(parents=True)
    payload = {
        "batch_id": batch,
        "ordinal": 1,
        "sites": [setup.site.to_dict() for setup in setups],
    }
    (batch_dir / M.INPUT_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    lanes = [
        M.LaneAssignment(
            site_id=setup.site.site_id,
            lane=setup.lane,
            sources=tuple(setup.sources),
            detail="assigned by the test",
        )
        for setup in setups
    ]
    (batch_dir / M.LANES_FILE).write_text(M.dump_jsonl(lanes), encoding="utf-8")
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    for setup in setups:
        for source_id, (doc, text) in setup.sources.items():
            store.write(
                site_id=setup.site.site_id,
                feature=M.source_feature(source_id, "txt"),
                body=text.encode("utf-8"),
            )
            store.write(
                site_id=setup.site.site_id,
                feature=M.source_feature(source_id, "meta"),
                body=doc.to_json().encode("utf-8"),
            )
    return batch_dir


#: What the Opus handoff declares for every answer: no meter, zeros that say so.
USAGE = MS.Usage.unmetered()


class ScriptedRunner:
    """The `ModelRunner` seam, answering from a script keyed by `(site_id, field)`.

    Like `HandoffRunner` it takes a `ModelCall` and nothing else, and it raises what a runner may
    raise: a scripted `UnreadableStream` or `ModelCallFailed` is raised instead of answered. A call
    that is not in the script is a test error, not an empty answer.
    """

    def __init__(self, script: Mapping[tuple[str, str], str | Exception]) -> None:
        self.script = dict(script)
        self.calls: list[MS.ModelCall] = []

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        if not isinstance(call, MS.ModelCall):
            raise TypeError(f"a runner takes a ModelCall, not {type(call).__name__}")
        self.calls.append(call)
        answer = self.script[(call.site_id, call.answer_key)]
        if isinstance(answer, Exception):
            raise answer
        return MS.ModelAnswer(text=answer, usage=USAGE)


def ledger_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def holds_of(batch_dir: Path) -> list[M.Hold]:
    path = batch_dir / M.HOLDS_FILE
    return M.load_jsonl(path, M.Hold) if path.exists() else []

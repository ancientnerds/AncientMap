"""Does the Phase-4 verifier (WB-C2) hold every site that breaks one of V1-V15, and only those?

`scripts/remediation/phase4/verify4.py` is the last deterministic line before a description is
written: it must pass a site whose every byte re-derives from its pinned source, and hold - under
the rule's own id - a site that breaks one property. The cases here build one clean site per lane
(W, T and R) and break exactly one thing each: a text, a hash, a marker, a span, a card word. They
break the *world*, not the record shape `model4` already refuses (PHASE4_CONTRACTS.md section 2).

The expected published strings are written out by hand below, never computed with the module's own
edit list, so a wrong edit list cannot move the expectation with it. Nothing here opens a socket,
reads the gitignored fonts, calls a model or touches a database: the card's font measurement goes
through a fake that measures with a real FreeType face (Pillow's own) and refuses the glyphs a
Latin font lacks, and the real brand fonts are tried only where they already are on disk.

The mutation cases are `p4 verify4: ...` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import sys
import types
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PIL import ImageFont

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

import phase4  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3.run import Batch  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import verify4 as V  # noqa: E402

from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS, listed_domain_of  # noqa: E402
from pipeline.video import shorts_audit, shorts_brand  # noqa: E402

VERIFY4 = PHASE4_PARENT / "phase4" / "verify4.py"
SITE_ID = "4a5a324f-1111-4111-8111-111111111111"
HEX_RAW = hashlib.sha256(b"the raw response").hexdigest()


def sha(text: str) -> str:
    """sha256 of the UTF-8 bytes, lowercase hex - written out here, not taken from `model4`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------
# Lane W: the pinned English article, its offered spans and the published text, by hand
# ------------------------------------------------------------------------------------------------

S1 = (
    "The Tarxien Temples are an archaeological complex of four megalithic structures, built "
    "between 3600 and 2500 BC, near the village of Tarxien."
)
S2 = (
    "The site was excavated in 1915 by Themistocles Zammit (the director of the museum), who "
    "found statues and altars."
)
S3 = "It contains a large statue of a fertility goddess and carved spiral reliefs."
S4 = "In 1992, the temples were declared a World Heritage Site as part of the Megalithic Temples."
S5 = "The temples were not built at once, and the earliest phase may date to 3600 BC."
TEXT = f"{S1} {S2} {S3} {S4}\n\n\n== History ==\n{S5}"

A1 = ", built between 3600 and 2500 BC,"  # S1: a paired-comma insertion
P2 = " (the director of the museum)"  # S2: a parenthesis with the space before it
T2 = ", who found statues and altars"  # S2: the last comma segment
L4 = "In 1992, "  # S4: a leading phrase
T4 = ", the temples were declared a World Heritage Site as part of the Megalithic Temples"

PUB1 = (
    "The Tarxien Temples are an archaeological complex of four megalithic structures near the "
    "village of Tarxien."
)
PUB2 = "The site was excavated in 1915 by Themistocles Zammit, who found statues and altars."
PUB3 = S3
CARD = PUB1

PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
STORED = (
    "Tarxien Temples is a group of megalithic temples in Malta dating from about 3150 BC [1]. "
    "The site was discovered in 1914 by local farmers and excavated by Themistocles Zammit, who "
    "found carved altars, a colossal statue of a fertility goddess and spiral reliefs [1]. It is "
    "part of a World Heritage Site [1]."
)
OLD_RAW: dict[str, Any] = {
    "description_citations": [
        {
            "n": 1,
            "url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
            "title": "Wikipedia",
            "domain": "en.wikipedia.org",
            "claim": "megalithic temples",
        }
    ],
    "heritage": {"unesco": True},
}


@dataclass(frozen=True)
class Pick:
    """One published sentence: its source sentence, the pieces dropped from it, the result."""

    sentence: str
    drops: tuple[str, ...]
    published: str  #: without its marker, ending in '.'


W_PICKS = (Pick(S1, (A1,), PUB1), Pick(S2, (P2,), PUB2), Pick(S3, (), PUB3))


def locate(text: str, sentence: str) -> tuple[int, int]:
    start = text.index(sentence)
    return start, start + len(sentence)


def piece_range(text: str, sentence: str, piece: str) -> tuple[int, int]:
    start, end = locate(text, sentence)
    at = text.index(piece, start, end)
    return at, at + len(piece)


def with_marker(published: str, n: int) -> str:
    assert published.endswith(".")
    return f"{published[:-1]} [{n}]."


def gate(verdict: str = "own", **over: Any) -> M.SubjectGate:
    values: dict[str, Any] = {
        "qid_match": True,
        "shared": verdict == "shared",
        "concept": False,
        "place_item": False,
        "km": 0.4,
        "name_score": 100.0,
        "verdict": M.SubjectVerdict(verdict),
    }
    values.update(over)
    return M.SubjectGate(**values)


def wiki_meta(source_id: str, text: str, *, lang: str, title: str, revid: int, **over: Any):
    permalink = (
        f"https://{lang}.wikipedia.org/w/index.php?title={title.replace(' ', '_')}&oldid={revid}"
    )
    doc = M.SourceDoc(
        id=source_id,
        url=f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        permalink=permalink,
        title=title,
        pageid=4242,
        revid=revid,
        lastrevid=revid,
        rev_timestamp="2026-09-01T10:00:00Z",
        retrieved_at="2026-09-23T08:00:00Z",
        sha256_raw=HEX_RAW,
        sha256_text=sha(text),
        licence=M.Licence.CC_BY_SA_4,
        route=M.Route.ENWIKI_TITLE,
        subject_gate=over.pop("subject_gate", gate()),
        tdm=None,
        final_url=None,
        truncated=None,
    )
    return {**doc.to_dict(), **over}


def plan_site(**over: Any) -> M.PlanSite:
    values: dict[str, Any] = {
        "site_id": SITE_ID,
        "name": "Tarxien Temples",
        "aliases": ("Tarxien",),
        "country": "Malta",
        "site_type": "Temple",
        "period_start": -3600,
        "period_end": None,
        "lat": 35.869,
        "lon": 14.512,
        "description": STORED,
        "description_sha256": sha(STORED),
        "raw_data": OLD_RAW,
        "raw_data_sha256": HEX_RAW,
        "card": "An old card.",
        "card_sha256": sha("An old card."),
        "source_url": "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "wikidata_qid": "Q1353330",
        "enwiki_title": "Tarxien Temples",
        "snapshot_description": None,
        "flags": frozenset(),
    }
    values.update(over)
    return M.PlanSite(**values)


@dataclass
class Case:
    """One site's verification inputs; `run()` is `verify_site` over them."""

    site: M.PlanSite
    assembly: M.Assembly
    metas: dict[str, dict[str, Any]]
    texts: dict[str, str]
    quotes: list[str]
    new_raw_data: dict[str, Any] = field(default_factory=dict)

    def run(self) -> tuple[M.Hold, ...]:
        return V.verify_site(
            self.site,
            self.assembly,
            metas=self.metas,
            texts=self.texts,
            quotes=self.quotes,
            new_raw_data=self.new_raw_data,
        )

    def reasons(self) -> set[str]:
        return {hold.reason.value for hold in self.run()}

    def detail(self, reason: str) -> str:
        return " | ".join(h.detail for h in self.run() if h.reason.value == reason)

    def replace(self, **over: Any) -> Case:
        """The same site with the assembly's fields replaced; raw_data follows the assembly."""
        assembly = dataclasses.replace(self.assembly, **over)
        return dataclasses.replace(
            self, assembly=assembly, new_raw_data=new_raw(self.site, assembly)
        )


def new_raw(site: M.PlanSite, assembly: M.Assembly) -> dict[str, Any]:
    """What `write4.new_raw_data` returns by contract (PHASE4_CONTRACTS.md section 5, Track D)."""
    out = dict(site.raw_data or {})
    out[M.CITATIONS_KEY] = [citation.to_dict() for citation in assembly.citations]
    out[M.PROVENANCE_KEY] = assembly.provenance.to_dict()
    return out


def make_case(
    *,
    lane: str = "W",
    text: str = TEXT,
    picks: tuple[Pick, ...] = W_PICKS,
    card: str | None = CARD,
    card_items: tuple[tuple[int, tuple[str, ...]], ...] = ((0, (A1,)),),
    site: M.PlanSite | None = None,
    subject_gate: M.SubjectGate | None = None,
) -> Case:
    """A clean lane-W or lane-S site (lane S: the W source under a 'shared' verdict)."""
    site = site or plan_site()
    verdict = gate("shared" if lane == "S" else "own")
    meta = wiki_meta(
        "W",
        text,
        lang="en",
        title="Tarxien Temples",
        revid=1234567,
        subject_gate=subject_gate or verdict,
    )
    sentences = []
    for pick in picks:
        start, end = locate(text, pick.sentence)
        drop = tuple(sorted(piece_range(text, pick.sentence, d) for d in pick.drops))
        sentences.append(M.PublishedSentence(n=1, src="W", start=start, end=end, drop=drop))
    description = " ".join(with_marker(pick.published, 1) for pick in picks)
    card_record = None
    if card is not None:
        items = tuple(
            M.CardItem(
                sentence=index,
                drop=tuple(sorted(piece_range(text, picks[index].sentence, d) for d in drops)),
            )
            for index, drops in card_items
        )
        card_record = M.Card(items=items, text_sha256=sha(card))
    provenance = M.Provenance(
        run="pilot-20260923",
        lane=M.Lane(lane),
        ai=M.AiMark.SELECTED,
        ai_system=M.AI_SYSTEM,
        licence=M.Licence.CC_BY_SA_4,
        attribution=M.Attribution(
            title="Tarxien Temples",
            url=PERMALINK,
            licence_url=M.PUBLISHED_LICENCE_URL,
            changes=M.Changes.SELECTED_AND_SHORTENED,
        ),
        sources=(
            M.SourceRef(
                id="W",
                url=PERMALINK,
                revid=1234567,
                rev_timestamp="2026-09-01T10:00:00Z",
                text_sha256=sha(text),
                licence=M.Licence.CC_BY_SA_4,
            ),
        ),
        sentences=tuple(sentences),
        card=card_record,
        desc_sha256=sha(description),
    )
    assembly = M.Assembly(
        site_id=site.site_id,
        description=description,
        citations=(
            M.Citation(
                n=1,
                url=PERMALINK,
                title="Wikipedia: Tarxien Temples",
                domain="en.wikipedia.org",
                license=M.Licence.CC_BY_SA_4,
            ),
        ),
        card=card,
        provenance=provenance,
    )
    return Case(
        site=site,
        assembly=assembly,
        metas={"W": meta},
        texts={"W": text},
        quotes=[text[s.start : s.end] for s in sentences],
        new_raw_data=new_raw(site, assembly),
    )


# ------------------------------------------------------------------------------------------------
# Lanes T and R: generated English over a pinned French article or a restricted page
# ------------------------------------------------------------------------------------------------

FR1 = "Le temple de Tarxien fut construit vers 3600 et fouillé en 1915 par Themistocles Zammit."
FR2 = "Les fouilles ont livré des statues, des autels et des reliefs sculptés de spirales."
FR3 = "Le site compte quatre structures mégalithiques reliées par des cours intérieures."
FR_TEXT = f"{FR1} {FR2} {FR3}"
EN1 = "The temple of Tarxien was built around 3600 and excavated in 1915 by Themistocles Zammit."
EN2 = "The excavations yielded statues, altars and carved reliefs of spirals."
EN3 = "The site has four megalithic structures linked by inner courtyards."
FR_PERMALINK = "https://fr.wikipedia.org/w/index.php?title=Temples_de_Tarxien&oldid=7654321"

Q1 = "The Tarxien Temples complex, dated to around 3150 BC, contains four megalithic temples."
Q2 = "Its southern temple preserves altars decorated with running spirals and animal friezes."
Q3 = "The temples were excavated by Themistocles Zammit between 1915 and 1919."
PAGE = f"{Q1} {Q2} Visitors reach the site from Paola on foot. {Q3}"
R1 = "Tarxien holds four megalithic temples that were built around 3150 BC."
R2 = "Altars in the southern temple carry carved spirals and friezes of animals."
R3 = "Themistocles Zammit led the digging of the temples from 1915 until 1919."
R_URL = "https://www.heritagemalta.mt/explore/tarxien-temples/"


def make_generated_case(lane: str) -> Case:
    """A clean lane-T (French article, translated) or lane-R (restricted page, restated) site."""
    site = plan_site()
    if lane == "T":
        source_id, text, quotes, published = "T.fr", FR_TEXT, (FR1, FR2, FR3), (EN1, EN2, EN3)
        meta = wiki_meta(source_id, text, lang="fr", title="Temples de Tarxien", revid=7654321)
        url, title, citation_title = (
            FR_PERMALINK,
            "Temples de Tarxien",
            "Wikipedia: Temples de Tarxien",
        )
        licence, revid, stamp = M.Licence.CC_BY_SA_4, 7654321, "2026-09-01T10:00:00Z"
        changes = M.Changes.TRANSLATED
    else:
        source_id, text, quotes, published = "R1", PAGE, (Q1, Q2, Q3), (R1, R2, R3)
        meta = M.SourceDoc(
            id="R1",
            url=R_URL,
            permalink=None,
            title="Tarxien Temples - Heritage Malta",
            pageid=None,
            revid=None,
            lastrevid=None,
            rev_timestamp=None,
            retrieved_at="2026-09-23T08:00:00Z",
            sha256_raw=HEX_RAW,
            sha256_text=sha(text),
            licence=M.Licence.RESTRICTED,
            route=M.Route.MINIMAX,
            subject_gate=None,
            tdm=M.Tdm(checked=True, reserved=False, signal=None),
            final_url=R_URL,
            truncated=False,
        ).to_dict()
        url, title = R_URL, "Tarxien Temples - Heritage Malta"
        citation_title = title
        licence, revid, stamp = M.Licence.RESTRICTED, None, None
        changes = M.Changes.FACTS_RESTATED
    sentences = tuple(
        M.PublishedSentence(n=1, src=source_id, start=a, end=b, drop=())
        for a, b in (locate(text, quote) for quote in quotes)
    )
    description = " ".join(with_marker(p, 1) for p in published)
    provenance = M.Provenance(
        run="pilot-20260923",
        lane=M.Lane(lane),
        ai=M.AiMark.GENERATED,
        ai_system=M.AI_SYSTEM,
        licence=M.PUBLISHED_LICENCE,
        attribution=M.Attribution(
            title=title, url=url, licence_url=M.PUBLISHED_LICENCE_URL, changes=changes
        ),
        sources=(
            M.SourceRef(
                id=source_id,
                url=url,
                revid=revid,
                rev_timestamp=stamp,
                text_sha256=sha(text),
                licence=licence,
            ),
        ),
        sentences=sentences,
        card=None,
        desc_sha256=sha(description),
    )
    domain = "fr.wikipedia.org" if lane == "T" else "www.heritagemalta.mt"
    assembly = M.Assembly(
        site_id=site.site_id,
        description=description,
        citations=(M.Citation(n=1, url=url, title=citation_title, domain=domain, license=licence),),
        card=None,
        provenance=provenance,
    )
    return Case(
        site=site,
        assembly=assembly,
        metas={source_id: meta},
        texts={source_id: text},
        quotes=list(quotes),
        new_raw_data=new_raw(site, assembly),
    )


def reprovenance(case: Case, **over: Any) -> Case:
    """The case with provenance fields replaced (desc_sha256 kept honest)."""
    provenance = dataclasses.replace(case.assembly.provenance, **over)
    return case.replace(provenance=provenance)


def republish(case: Case, description: str) -> Case:
    """The case with another published description, its hash kept honest (V13 stays quiet)."""
    provenance = dataclasses.replace(case.assembly.provenance, desc_sha256=sha(description))
    return case.replace(description=description, provenance=provenance)


# ------------------------------------------------------------------------------------------------
# Seams: the card's font measurement, and the two modules of other tracks
# ------------------------------------------------------------------------------------------------

#: A real FreeType face (Pillow's own), at the caption size the short draws.
CAPTION_FACE = ImageFont.load_default(size=shorts_audit.CAPTION_SIZE)
#: What the fake face covers: Basic Latin to Latin Extended-A, as JetBrains Mono does. U+02BF
#: (`Jabal al-ʿHayn`, plan section 7, S4) lies outside it, as it lies outside both brand fonts.
FAKE_CMAP_LAST = 0x017F


def fake_card_fit(name: str, card: str) -> V.CardFit:
    """`card_fit` without the gitignored brand fonts: missing glyphs from a fixed Latin cmap, the
    widest word measured by the real `shorts_audit.widest_word_px` with a real face."""
    shown = f"{name} {card}"
    missing = tuple(sorted({ch for ch in shown if not ch.isspace() and ord(ch) > FAKE_CMAP_LAST}))
    widest, px = shorts_audit.widest_word_px(card.split(), CAPTION_FACE)
    return V.CardFit(missing=missing, widest=widest, px=px)


#: The one test that measures with the real brand fonts, where they are on disk.
REAL_FONTS_TEST = "test_v10_measures_through_the_shorts_own_helpers_with_the_brand_fonts"


@pytest.fixture(autouse=True)
def _card_fit_without_brand_fonts(request: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name != REAL_FONTS_TEST:
        monkeypatch.setattr(V, "card_fit", fake_card_fit)


#: The design's AI aggregators and Wikipedia mirrors (source_store, "DENY LIST").
_AI_AGGREGATORS = ("grokipedia.com", "aroundus.com", "mindtrip.ai", "evendo.com", "wanderlog.com")
_MIRRORS = ("kiddle.co", "wikiwand.com", "dbpedia.org", "alchetron.com", "wiki2.org")


def _licences_stand_in() -> types.ModuleType:
    """Track A's `phase4.licences.deny_family` as the contract states it (PHASE4_CONTRACTS.md
    section 5, Track A): an AI aggregator, a Wikipedia mirror or `BLOCKED_DOMAINS`, else None.
    Used only while WB-A2 is not on this branch; once it is, the real module is tested."""
    from urllib.parse import urlsplit

    module = types.ModuleType("phase4.licences")

    def deny_family(url: str) -> str | None:
        if not isinstance(url, str):
            raise TypeError(f"{url!r} is not a URL")
        host = (urlsplit(url).hostname or "").lower()
        if listed_domain_of(host, _AI_AGGREGATORS):
            return "ai-aggregator"
        if listed_domain_of(host, _MIRRORS):
            return "wikipedia-mirror"
        if listed_domain_of(host, BLOCKED_DOMAINS):
            return "blocked"
        return None

    module.deny_family = deny_family  # type: ignore[attr-defined]
    return module


def _write4_stand_in() -> types.ModuleType:
    """Track D's `phase4.write4.new_raw_data` as the contract states it; only while WB-D2 is not
    on this branch."""
    module = types.ModuleType("phase4.write4")

    def new_raw_data(old: dict[str, Any] | None, assembly: M.Assembly) -> dict[str, Any]:
        if not isinstance(assembly, M.Assembly):
            raise TypeError(f"{assembly!r} is not an Assembly")
        return new_raw(dataclasses.replace(plan_site(), raw_data=old), assembly)

    module.new_raw_data = new_raw_data  # type: ignore[attr-defined]
    return module


def _other_track(monkeypatch: pytest.MonkeyPatch, name: str, stand_in: types.ModuleType) -> None:
    if importlib.util.find_spec(f"phase4.{name}") is None:
        monkeypatch.setitem(sys.modules, f"phase4.{name}", stand_in)
        monkeypatch.setattr(phase4, name, stand_in, raising=False)


@pytest.fixture
def licences(monkeypatch: pytest.MonkeyPatch) -> None:
    _other_track(monkeypatch, "licences", _licences_stand_in())


@pytest.fixture
def write4(monkeypatch: pytest.MonkeyPatch) -> None:
    _other_track(monkeypatch, "write4", _write4_stand_in())


# ------------------------------------------------------------------------------------------------
# Independence
# ------------------------------------------------------------------------------------------------


def test_the_verifier_never_imports_the_assembler() -> None:
    """WB-C2: an AST scan of every import, at any depth, including a dynamic one."""
    tree = ast.parse(VERIFY4.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            assert name not in {"import_module", "__import__"}, "a dynamic import in verify4"
    assert imported, "the scan found no import at all - it is not scanning the module"
    assert not [name for name in imported if name.split(".")[-1] == "assemble"], imported


def test_the_ast_scan_would_see_an_import_of_the_assembler() -> None:
    """The scan above is not vacuous: the same walk finds each spelling of the import."""
    for source in (
        "from phase4 import assemble",
        "from phase4.assemble import assemble",
        "import phase4.assemble as A",
        "def f():\n    from phase4 import assemble\n",
    ):
        names = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
        assert [n for n in names if n.split(".")[-1] == "assemble"], source


# ------------------------------------------------------------------------------------------------
# The span finder and the edit list (the verifier's own reading)
# ------------------------------------------------------------------------------------------------


def _offered(sentence: str) -> list[str]:
    return [sentence[a:b] for a, b in V.offered_spans(sentence, 0, len(sentence))]


def test_the_designs_own_example_is_offered_with_its_delimiter() -> None:
    """writer, User block: `a1=", whose tomb lies nearby"`; `c.` keeps the date out of reach."""
    sentence = "The temple was built c. 2500 BC by Khufu, whose tomb lies nearby."
    assert _offered(sentence) == [", whose tomb lies nearby"]


def test_every_span_kind_is_offered_as_the_range_it_removes() -> None:
    assert _offered(S1) == [A1, ", near the village of Tarxien"]
    assert _offered(S2) == [P2, T2]
    assert _offered(S4) == [L4]  # T4 carries 'part of'
    dashed = "The fort – built by the Romans – was abandoned in the 5th century."
    assert _offered(dashed) == [" – built by the Romans –"]


def test_a_span_with_a_protected_token_is_never_offered() -> None:
    sentence = (
        "The wall, which was not finished, stands (possibly) on older footings, suggesting reuse."
    )
    assert _offered(sentence) == ["The wall, "]  # the one span without a protected token
    assert V.protected_in(", which was not finished,") == ("not",)
    assert V.protected_in(", suggesting reuse") == ("suggest*",)
    assert V.protected_in("part  of the") == ("part of",)
    assert V.protected_in("dated c. 2500 BC") == ("c.",)
    assert V.protected_in("the etc. list") == ()


def test_a_number_comma_and_a_bracketed_comma_are_no_delimiters() -> None:
    sentence = "The hoard of 2,500 coins (found in 1920, near the gate) lies in the museum store."
    assert _offered(sentence) == [" (found in 1920, near the gate)"]


def test_an_unspaced_dash_pair_is_not_offered() -> None:
    assert _offered("The fort—built by the Romans—was abandoned in the 5th century AD.") == []


def test_a_leading_phrase_is_at_most_six_tokens() -> None:
    seven = "In the very late summer of 1920, the site was excavated by a team."
    assert "In the very late summer of 1920, " not in _offered(seven)
    six = "In the late summer of 1920, the site was excavated by a team."
    assert "In the late summer of 1920, " in _offered(six)


def test_the_edit_list_removes_repairs_restores_and_marks() -> None:
    start, end = locate(TEXT, S4)
    low, high = piece_range(TEXT, S4, L4)
    assert V.edited(TEXT, start, end, [(low, high)]).startswith("The temples were declared")
    text = "The pit (x) , a hearth  and a wall (y) were found."
    assert (
        V.edited(text, 0, len(text), [(8, 11), (35, 39)])
        == "The pit, a hearth and a wall were found."
    )
    assert V.marked("He called it the old fort.", 2) == "He called it the old fort [2]."
    assert V.marked('It is called "the fort."', 1) == 'It is called "the fort [1]."'
    assert V.marked("No final stop", 1) is None


def test_the_card_speaks_circa_and_nothing_else() -> None:
    assert V.spoken("Built c. 2500 BC and ca.300 AD, etc. in B.C. times.") == (
        "Built circa 2500 BC and circa 300 AD, etc. in B.C. times."
    )
    assert V.spoken("C. 2500 BC it was built.") == "Circa 2500 BC it was built."


# ------------------------------------------------------------------------------------------------
# The clean sites
# ------------------------------------------------------------------------------------------------


def test_a_clean_lane_w_site_passes_every_rule() -> None:
    case = make_case()
    assert len(V.without_markers(case.assembly.description)) >= V.DESCRIPTION_MIN
    assert V.CARD_MIN <= len(CARD) <= V.CARD_MAX
    assert case.run() == ()


def test_a_clean_lane_t_site_passes_every_rule() -> None:
    assert make_generated_case("T").run() == ()


def test_a_clean_lane_r_site_passes_every_rule(licences: None) -> None:
    assert make_generated_case("R").run() == ()


def test_a_hold_names_its_rule_its_site_and_what_broke() -> None:
    case = make_case()
    broken = dataclasses.replace(case, texts={"W": TEXT.replace("Tarxien.", "Tarxien!")})
    holds = broken.run()
    assert {h.site_id for h in holds} == {SITE_ID}
    assert all(h.detail for h in holds)
    assert "V1" in {h.reason.value for h in holds}


def test_an_assembly_of_another_site_is_refused() -> None:
    case = make_case()
    other = dataclasses.replace(case.assembly, site_id="another-site")
    with pytest.raises(ValueError, match="is not the site"):
        V.verify_site(
            case.site,
            other,
            metas=case.metas,
            texts=case.texts,
            quotes=case.quotes,
            new_raw_data={},
        )


# ------------------------------------------------------------------------------------------------
# V1 pin
# ------------------------------------------------------------------------------------------------


def test_v1_a_text_that_is_not_the_pinned_one_is_held() -> None:
    case = make_case()
    case.metas["W"]["sha256_text"] = sha(TEXT + " ")
    assert "V1" in case.reasons()
    assert "the stored text hashes to" in case.detail("V1")


def test_v1_a_revision_that_is_not_an_integer_is_held() -> None:
    """Read from the raw meta: `model4.SourceDoc` would refuse a bool first (contract section 2)."""
    case = make_case()
    case.metas["W"]["revid"] = True
    case.metas["W"]["lastrevid"] = True
    assert "is not an integer" in case.detail("V1")


def test_v1_a_revision_that_moved_is_held() -> None:
    case = make_case()
    case.metas["W"]["lastrevid"] = 1234568
    assert "is not lastrevid" in case.detail("V1")


def test_v1_a_url_that_is_not_an_oldid_permalink_is_held() -> None:
    assert V.is_permalink(PERMALINK, lang="en", revid=1234567)
    for url in (
        "https://en.wikipedia.org/wiki/Tarxien_Temples",
        "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234568",
        "https://fr.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567",
        "http://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567",
        "https://en.wikipedia.org/w/index.php?title=&oldid=1234567",
        "https://en.wikipedia.org/w/index.php?title=X&oldid=1234567&action=raw",
    ):
        assert not V.is_permalink(url, lang="en", revid=1234567), url
    case = make_case()
    case.metas["W"]["permalink"] = "https://en.wikipedia.org/wiki/Tarxien_Temples"
    assert "is not the oldid permalink" in case.detail("V1")


def test_v1_lanes_w_s_and_t_publish_only_from_cc_by_sa_wikipedia() -> None:
    case = make_case()
    case.metas["W"]["licence"] = "CC BY 4.0"
    assert "publish from CC BY-SA 4.0 Wikipedia only" in case.detail("V1")


def test_v1_a_lane_that_cites_a_source_of_another_kind_is_held(licences: None) -> None:
    case = make_generated_case("R")
    provenance = case.assembly.provenance
    provenance = dataclasses.replace(
        provenance,
        lane=M.Lane.T,
        attribution=dataclasses.replace(provenance.attribution, changes=M.Changes.TRANSLATED),
    )
    assert "publishes from" in case.replace(provenance=provenance).detail("V1")


def test_v1_a_restricted_page_on_the_deny_list_is_held(licences: None) -> None:
    case = make_generated_case("R")
    denied = "https://grokipedia.com/page/Tarxien_Temples"
    case.metas["R1"]["url"] = denied
    assert "is on the deny list" in case.detail("V1")


def test_v1_the_attribution_names_the_article_it_links() -> None:
    case = make_case()
    attribution = dataclasses.replace(case.assembly.provenance.attribution, title="Ħal Tarxien")
    assert "attribution names" in reprovenance(case, attribution=attribution).detail("V1")


# ------------------------------------------------------------------------------------------------
# V2 quote, V3 assembly, V4 drop legality
# ------------------------------------------------------------------------------------------------


def test_v2_a_quote_that_is_not_the_source_slice_is_held() -> None:
    case = make_case()
    case.quotes[1] = case.quotes[1].replace("1915", "1916")
    assert "is not the quote" in case.detail("V2")


def test_v2_a_quote_that_does_not_occur_in_the_text_is_held() -> None:
    """The text carries a decomposed 'é' (NFD): the NFC slice equals the quote, the page does not
    carry it, and only `discover_stage.quote_occurs` notices."""
    sentence = "The Café Tarxien tomb was opened in 1915 by Themistocles Zammit and his team."
    text = unicodedata.normalize("NFD", sentence) + " " + S3
    nfd_sentence = unicodedata.normalize("NFD", sentence)
    case = make_case(
        text=text,
        picks=(Pick(nfd_sentence, (), nfd_sentence), Pick(S3, (), S3)),
        card=None,
    )
    case.quotes[0] = unicodedata.normalize("NFC", case.quotes[0])
    assert "does not occur" in case.detail("V2")


def test_v2_every_published_sentence_needs_its_quote() -> None:
    case = make_case()
    case.quotes.pop()
    assert "2 quote(s) for 3 published sentence(s)" in case.detail("V2")


def test_v3_a_published_sentence_the_edit_list_does_not_rebuild_is_held() -> None:
    case = make_case()
    changed = case.assembly.description.replace("four megalithic", "five megalithic")
    assert "rebuilt" in republish(case, changed).detail("V3")


def test_v3_a_description_that_does_not_split_into_its_sentences_is_held() -> None:
    case = make_case()
    glued = case.assembly.description.replace(" [1]. The site", ". The site", 1)
    held = republish(case, glued)
    assert "marker-terminated sentence(s)" in held.detail("V3")
    assert "V8" in held.reasons()


def test_v3_lane_r_drops_nothing_from_a_quote(licences: None) -> None:
    case = make_generated_case("R")
    first = case.assembly.provenance.sentences[0]
    cut = dataclasses.replace(first, drop=((first.start + 3, first.start + 11),))
    sentences = (cut, *case.assembly.provenance.sentences[1:])
    assert "drops nothing" in reprovenance(case, sentences=sentences).detail("V3")


def test_v4_a_drop_that_is_not_an_offered_span_is_held() -> None:
    case = make_case(picks=(Pick(S1, (" megalithic",), "x."), *W_PICKS[1:]))
    assert "is not an offered span" in case.detail("V4")


def test_v4_a_drop_that_removes_a_protected_token_is_held() -> None:
    published = "In 1992."
    case = make_case(picks=(*W_PICKS, Pick(S4, (T4,), published)), card_items=((0, (A1,)),))
    assert V.protected_in(T4) == ("part of",)
    assert "removes the protected ['part of']" in case.detail("V4")


def test_v4_a_card_that_keeps_a_span_its_sentence_dropped_is_held() -> None:
    case = make_case(card_items=((0, ()),), card=S1)
    holds = [h for h in case.run() if h.reason is M.HoldReason.V4]
    assert [h.scope for h in holds] == [M.HoldScope.CARD]
    assert "is not removed" in holds[0].detail


# ------------------------------------------------------------------------------------------------
# V5 well-formed, V6 anaphora and naming, V7 subject
# ------------------------------------------------------------------------------------------------


def test_v5_a_sentence_that_is_too_short_or_opens_small_is_held() -> None:
    short = "It was a temple site."
    text = f"{S1} {short}"
    case = make_case(
        text=text, picks=(W_PICKS[0], Pick(short, (), short)), card_items=((0, (A1,)),)
    )
    assert "characters, not 25-400" in case.detail("V5")
    small = "the stones were set upright in a line."
    text = f"{S1} {small}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(small, (), small)))
    assert "not a capital, digit or quote" in case.detail("V5")


def test_v5_an_extract_artefact_is_held() -> None:
    bad = "The temple (listen) was restored after the storm damage of 1956."
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert "artefact 'listen'" in case.detail("V5")


def test_v5_unbalanced_quotes_are_held() -> None:
    bad = 'The temple was called "the House of the Goddess by the villagers.'
    text = f"{S1} {bad}"
    case = make_case(text=text, picks=(W_PICKS[0], Pick(bad, (), bad)))
    assert "unbalanced" in case.detail("V5")
    assert V.balanced('He said "yes" and (then) left [1].')


def test_v6_a_pronoun_without_its_source_predecessor_is_held() -> None:
    case = make_case(picks=(W_PICKS[0], W_PICKS[2]))
    assert "opens with a pronoun" in case.detail("V6")
    assert V.opens_with_pronoun("The latter was built later.")
    assert not V.opens_with_pronoun("Items were found.")
    assert not V.opens_with_pronoun("Thereafter it was used.")


def test_v6_the_first_sentence_must_name_the_site() -> None:
    case = make_case(picks=(W_PICKS[1], W_PICKS[2]), card=None)
    assert "sentence 1 names none" in case.detail("V6")


def test_v6_the_name_match_is_directional() -> None:
    assert V.name_in("Tarxien Temples", "The Tarxien temples lie in Paola.")
    assert not V.name_in("Kilmartin Glen standing stones", "Kilmartin is a village.")
    assert V.name_in("Kilmartin", "Kilmartin Glen standing stones are old.")


def test_v6_the_article_title_counts_only_for_a_strong_own_verdict() -> None:
    site = plan_site(name="Ħal Tarxien megaliths", aliases=())
    strong = make_case(site=site, card=None)
    assert "V6" not in strong.reasons()  # 'Tarxien Temples', the title, is in sentence 1
    weak = make_case(site=site, card=None, subject_gate=gate(km=None))
    assert "sentence 1 names none" in weak.detail("V6")


def test_v7_a_verdict_that_does_not_allow_the_lane_is_held() -> None:
    case = make_case(subject_gate=gate("shared"))
    assert "lane W needs 'own'" in case.detail("V7")


def test_v7_lane_s_publishes_only_name_bearing_or_matching_section_sentences() -> None:
    case = make_case(lane="S", picks=(W_PICKS[0], W_PICKS[1]), card=None)
    assert "sentence 2: lane S" in case.detail("V7")
    under_history = make_case(
        lane="S",
        picks=(W_PICKS[0], Pick(S5, (), S5)),
        card=None,
        site=plan_site(aliases=("Tarxien", "Tarxien history")),
    )
    assert "V7" not in under_history.reasons()
    assert V.heading_before(TEXT, TEXT.index(S5)) == "History"


# ------------------------------------------------------------------------------------------------
# V8 markers, V9 length, V10 card
# ------------------------------------------------------------------------------------------------


def test_v8_a_marker_without_a_citation_is_held() -> None:
    case = make_case()
    wrong = case.assembly.description.replace("Tarxien [1].", "Tarxien [2].", 1)
    held = republish(case, wrong)
    assert "have no citation" in held.detail("V8")


def test_v8_citations_are_numbered_by_first_appearance() -> None:
    case = make_case()
    sentences = tuple(dataclasses.replace(s, n=2) for s in case.assembly.provenance.sentences)
    description = case.assembly.description.replace("[1]", "[2]")
    citations = (dataclasses.replace(case.assembly.citations[0], n=2),)
    provenance = dataclasses.replace(
        case.assembly.provenance, sentences=sentences, desc_sha256=sha(description)
    )
    held = case.replace(description=description, citations=citations, provenance=provenance)
    assert "by first appearance it is [1]" in held.detail("V8")


def test_v8_a_citation_must_link_the_pinned_permalink() -> None:
    case = make_case()
    citations = (
        dataclasses.replace(
            case.assembly.citations[0], url="https://en.wikipedia.org/wiki/Tarxien_Temples"
        ),
    )
    assert "its source W is" in case.replace(citations=citations).detail("V8")


def test_v9_a_description_that_is_too_short_or_under_the_floor_is_held() -> None:
    case = make_case(picks=(W_PICKS[0], W_PICKS[1]), card=CARD)
    assert "not 200-1100" in case.detail("V9")
    long_stored = plan_site(description=STORED * 3, description_sha256=sha(STORED * 3))
    floor = make_case(site=long_stored)
    assert "under half the stored" in floor.detail("V9")
    waived = make_case(
        site=dataclasses.replace(long_stored, flags=frozenset({M.SiteFlag.T03_SEVERE}))
    )
    assert "V9" not in waived.reasons()


def test_v10_a_card_that_is_not_its_items_is_held() -> None:
    case = make_case()
    card = CARD.replace("four", "five")
    card_record = dataclasses.replace(case.assembly.provenance.card, text_sha256=sha(card))
    held = reprovenance(case, card=card_record).replace(card=card)
    holds = [h for h in held.run() if h.reason is M.HoldReason.V10]
    assert [h.scope for h in holds] == [M.HoldScope.CARD]
    assert "is not its items minus offered spans" in holds[0].detail


def test_v10_a_card_out_of_its_length_is_held() -> None:
    case = make_case(card=PUB2, card_items=((1, (P2,)),))  # 85 characters: a card
    assert "V10" not in case.reasons()
    short = "The site was excavated in 1915 by Themistocles Zammit."
    case = make_case(card=short, card_items=((1, (P2, T2)),))
    assert "not 80-200" in case.detail("V10")


def test_v10_a_card_that_names_a_country_is_held() -> None:
    sentence = (
        "The Tarxien Temples of Malta are a complex of four megalithic structures near Paola."
    )
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "names a country: ['Malta']" in case.detail("V10")
    assert V.card_countries("The Egyptian and Roman builders.", "Egypt") == []


def test_v10_a_card_with_an_evaluative_superlative_is_held() -> None:
    sentence = "The Tarxien Temples are one of the most elaborate megalithic complexes near Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "evaluative superlative(s) ['one of the most']" in case.detail("V10")


def test_v10_a_card_opening_with_a_pronoun_is_held() -> None:
    case = make_case(card=S3, card_items=((2, ()),))
    assert "opens with a pronoun" in case.detail("V10")


def test_v10_a_card_the_heading_font_cannot_draw_is_held() -> None:
    sentence = "The Tarxien Temples at Jabal al-ʿHayn are a complex of four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "cannot draw U+02BF" in case.detail("V10")


def test_v10_a_caption_word_wider_than_the_frame_is_held() -> None:
    word = "Tarxienmegalithicarchaeologicalcomplexes"
    sentence = f"The Tarxien Temples are an extraordinary {word} of four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert f"the caption word {word!r}" in case.detail("V10")


def test_v10_the_card_speaks_circa_where_the_description_writes_c() -> None:
    sentence = "The Tarxien Temples are a complex of four megalithic structures built c. 3150 BC."
    spoken = "The Tarxien Temples are a complex of four megalithic structures built circa 3150 BC."
    text = f"{sentence} {S2} {S3}"
    picks = (Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2])
    assert make_case(text=text, picks=picks, card=spoken, card_items=((0, ()),)).run() == ()
    held = make_case(text=text, picks=picks, card=sentence, card_items=((0, ()),))
    assert "is not its items" in held.detail("V10")


def test_v10_measures_through_the_shorts_own_helpers_with_the_brand_fonts() -> None:
    fonts = [shorts_brand.FONT_DIR / name for name in shorts_brand.FONTS]
    if not all(path.exists() for path in fonts):
        pytest.skip("the brand fonts (video-assets/fonts, gitignored) are not on this machine")
    pytest.importorskip("fontTools", reason="fontTools reads the brand fonts' cmap")
    fit = V.card_fit("Tarxien Temples", CARD)
    assert fit.missing == () and fit.widest == "archaeological"
    assert (
        fit.px
        == shorts_audit.widest_word_px(
            CARD.split(),
            shorts_audit.caption_font(shorts_brand.heading_font("Tarxien Temples " + CARD)),
        )[1]
    )
    assert V.card_fit("Jabal al-ʿHayn", "A card.").missing == ("ʿ",)


# ------------------------------------------------------------------------------------------------
# V11 closure, V12 raw_data, V13 hashes, V14 dates, V15 injection
# ------------------------------------------------------------------------------------------------


def _regenerate(case: Case, index: int, sentence: str) -> Case:
    published = [split.text for split in V.split_published(case.assembly.description) or ()]
    published[index] = sentence
    return republish(case, " ".join(with_marker(p, 1) for p in published))


def test_v11_a_translated_number_that_is_not_in_its_quote_is_held() -> None:
    case = _regenerate(make_generated_case("T"), 0, EN1.replace("3600", "3700"))
    assert "the numbers ['3700'] are not in its quote" in case.detail("V11")


def test_v11_a_capitalised_word_that_is_not_in_its_quote_is_held() -> None:
    case = _regenerate(make_generated_case("T"), 1, EN2.replace("statues", "Roman statues"))
    assert "['Roman'] are not in its quote" in case.detail("V11")


def test_v11_a_restated_year_whose_era_flipped_is_held(licences: None) -> None:
    case = _regenerate(make_generated_case("R"), 0, R1.replace("3150 BC", "3150 AD"))
    assert "the year '3150 AD' is not its quote's" in case.detail("V11")


def test_v11_an_r_quote_that_is_not_on_its_page_is_held(licences: None) -> None:
    case = make_generated_case("R")
    case.quotes[1] = case.quotes[1].replace("running spirals", "running lions")
    assert "quote does not occur" in case.detail("V11")


def test_v11_a_restatement_that_copies_eight_words_is_held(licences: None) -> None:
    copied = "Themistocles Zammit reported that the temples were excavated by Themistocles Zammit between 1915 and 1919."
    case = _regenerate(make_generated_case("R"), 2, copied)
    assert "copies" in case.detail("V11")


def test_v12_a_raw_data_that_changes_another_key_is_held() -> None:
    case = make_case()
    case.new_raw_data["heritage"] = {"unesco": False}
    assert "changes ['heritage']" in case.detail("V12")
    case = make_case()
    del case.new_raw_data["heritage"]
    assert "lost ['heritage']" in case.detail("V12")


def test_v12_empty_citations_would_let_the_boot_seed_fire() -> None:
    case = make_case()
    case.new_raw_data[M.CITATIONS_KEY] = []
    assert "re-seed could fire" in case.detail("V12")


def test_v12_the_provenance_written_is_the_assemblys() -> None:
    case = make_case()
    case.new_raw_data[M.PROVENANCE_KEY] = dict(case.new_raw_data[M.PROVENANCE_KEY], run="other")
    assert "is not the assembly's provenance" in case.detail("V12")


def test_v13_a_description_hash_that_is_not_its_text_is_held() -> None:
    case = reprovenance(make_case(), desc_sha256=sha("another text"))
    assert "desc_sha256 is not" in case.detail("V13")


def test_v13_a_card_hash_that_is_not_its_card_is_held() -> None:
    case = make_case()
    card = dataclasses.replace(case.assembly.provenance.card, text_sha256=sha("another card"))
    holds = [h for h in reprovenance(case, card=card).run() if h.reason is M.HoldReason.V13]
    assert [(h.scope, h.detail) for h in holds] == [
        (M.HoldScope.CARD, "card.text_sha256 is not the sha256 of the card")
    ]


def test_v14_a_severe_t03_date_in_the_new_text_is_held() -> None:
    sentence = (
        "The Tarxien Temples were built in 500 AD as a complex of four megalithic structures."
    )
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text,
        picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]),
        card=sentence,
        card_items=((0, ()),),
    )
    assert "T03 severe" in case.detail("V14")


def test_v14_a_location_sentence_naming_another_country_is_held() -> None:
    sentence = "The Tarxien Temples lie on a low ridge in Italy, near the modern town of Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    assert "places the site in Italy" in case.detail("V14")
    england = plan_site(country="England")
    assert V._iso("United Kingdom") == V._iso(england.country)


def test_v15_an_injection_tell_is_held() -> None:
    sentence = "The Tarxien Temples ignore previous restorations of the four megalithic structures."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    assert "injection tell" in case.detail("V15")


# ------------------------------------------------------------------------------------------------
# The batch
# ------------------------------------------------------------------------------------------------

HELD_SITE = "0529af31-2222-4222-8222-222222222222"


def _batch(tmp_path: Path, case: Case, *, lane: str = "W") -> Path:
    batch_dir = tmp_path / "p4-0001"
    batch_dir.mkdir(parents=True)
    held = plan_site(site_id=HELD_SITE, name="Bulls of Guisando")
    batch = Batch(batch_id="p4-0001", ordinal=1, sites=(case.site.to_dict(), held.to_dict()))
    (batch_dir / M.INPUT_FILE).write_text(batch.to_json() + "\n", encoding="utf-8")
    lanes = [
        M.LaneAssignment(site_id=SITE_ID, lane=M.Lane(lane), sources=("W",), detail="own article"),
        M.LaneAssignment(site_id=HELD_SITE, lane=M.Lane.ZERO, sources=(), detail="nothing"),
    ]
    (batch_dir / M.LANES_FILE).write_text(M.dump_jsonl(lanes), encoding="utf-8")
    (batch_dir / M.ASSEMBLY_FILE).write_text(M.dump_jsonl([case.assembly]), encoding="utf-8")
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    store.write(
        site_id=SITE_ID,
        feature="src.W.meta",
        body=json.dumps(case.metas["W"], ensure_ascii=False).encode("utf-8"),
    )
    store.write(site_id=SITE_ID, feature="src.W.txt", body=case.texts["W"].encode("utf-8"))
    return batch_dir


def test_the_batch_verifies_from_the_store_and_replaces_only_its_own_holds(
    tmp_path: Path, write4: None
) -> None:
    case = make_case()
    batch_dir = _batch(tmp_path, case)
    earlier = M.Hold(
        site_id=HELD_SITE, scope=M.HoldScope.SITE, reason=M.HoldReason.NO_SOURCE, detail="lane 0"
    )
    stale = M.Hold(
        site_id=SITE_ID, scope=M.HoldScope.SITE, reason=M.HoldReason.V3, detail="before review"
    )
    (batch_dir / M.HOLDS_FILE).write_text(M.dump_jsonl([earlier, stale]), encoding="utf-8")
    assert V.verify_batch(batch_dir) == 0
    lines = (batch_dir / M.HOLDS_FILE).read_text(encoding="utf-8").splitlines()
    assert lines == [earlier.to_json()]  # the other stage's line kept, the stale V3 gone
    assert (batch_dir / V.FIELD_CONFLICTS_FILE).read_text(encoding="utf-8") == ""


def test_the_batch_holds_what_the_store_does_not_pin(tmp_path: Path, write4: None) -> None:
    case = make_case()
    batch_dir = _batch(tmp_path, case)
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    text_path = store.path_for(SITE_ID, "src.W.txt")
    text_path.write_bytes(text_path.read_bytes().replace(b"Tarxien.", b"Tarxien!"))
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert "V1" in {hold.reason.value for hold in holds}


def test_the_batch_reads_the_text_as_bytes_not_as_translated_lines(
    tmp_path: Path, write4: None
) -> None:
    """A CRLF in the pinned text is a character offsets count; text mode would drop it."""
    text = TEXT.replace("\n\n\n== History ==\n", "\r\n\r\n== History ==\r\n")
    case = make_case(text=text)
    batch_dir = _batch(tmp_path, case)
    assert V.verify_batch(batch_dir) == 0
    assert M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold) == []


def test_the_batch_holds_a_site_whose_lane_is_not_the_assigned_one(
    tmp_path: Path, write4: None
) -> None:
    batch_dir = _batch(tmp_path, make_case(), lane="S")
    assert V.verify_batch(batch_dir) == 0
    holds = M.load_jsonl(batch_dir / M.HOLDS_FILE, M.Hold)
    assert any("S1b assigned S" in hold.detail for hold in holds if hold.reason is M.HoldReason.V7)


def test_the_batch_writes_v14_holds_to_the_field_conflicts_report(
    tmp_path: Path, write4: None
) -> None:
    sentence = "The Tarxien Temples lie on a low ridge in Italy, near the modern town of Paola."
    text = f"{sentence} {S2} {S3}"
    case = make_case(
        text=text, picks=(Pick(sentence, (), sentence), W_PICKS[1], W_PICKS[2]), card=None
    )
    batch_dir = _batch(tmp_path, case)
    assert V.verify_batch(batch_dir) == 0
    conflicts = M.load_jsonl(batch_dir / V.FIELD_CONFLICTS_FILE, M.Hold)
    assert [hold.reason for hold in conflicts] == [M.HoldReason.V14]


def test_a_batch_that_cannot_be_read_stops_the_run(tmp_path: Path, write4: None) -> None:
    batch_dir = _batch(tmp_path, make_case())
    (batch_dir / M.ASSEMBLY_FILE).unlink()
    assert V.verify_batch(batch_dir) == 2
    batch_dir2 = _batch(tmp_path / "x", make_case())
    (batch_dir2 / M.HOLDS_FILE).write_text("not a hold\n", encoding="utf-8")
    assert V.verify_batch(batch_dir2) == 2


def test_the_command_prints_its_own_exit_line(
    tmp_path: Path, write4: None, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _batch(tmp_path, make_case())
    assert V.main([str(batch_dir)]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "STAGE_EXIT=0"

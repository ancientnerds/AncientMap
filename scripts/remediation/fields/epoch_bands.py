"""Owner decision D136 (2026-11-07): the epoch -> period band table, written from the code.

`EPOCH_BANDS.md` is the owner's view of `pipeline.periods.epoch_band`: one row per epoch of
`PERIODS` (169 on 2026-11-07), its conventional span, the band its conventional start falls in,
and every country whose own start (`REGIONAL_STARTS`) puts it in another band. It is generated,
never edited, so the table the owner reads and the function that writes the year cannot drift.

    ./.venv/Scripts/python.exe scripts/remediation/fields/epoch_bands.py table [--out FILE]
    ./.venv/Scripts/python.exe scripts/remediation/fields/epoch_bands.py candidates         --sites live/undated_988.jsonl --resets live/d121_d122_reset.jsonl [--run DIR]

`candidates` (read-only, no model) finds, for each undated site, an epoch word in the site's OWN
evidence, in the order D136's task names: (1) the verbatim `found` quotes of earlier lanes'
period_start answers (every `ATTEMPTS.jsonl`/`DECISIONS.jsonl` under `fields/`, the wd5r pilots,
the D113 conflict list), (2) the D121/D122 reset rows (kept as context: a corpus-wide site_type rule
is not the site's own evidence, D136 supersedes D122 only where the site's own sources, P2348 or its
own type/name name an epoch), (3) Wikidata P2348 of the item, (4) the site's own site_type and name,
(5) the lead of its cached English Wikipedia article. A sentence counts only as the D70 extractor
reads one (`fields.dating.sentence_candidates`): anchored on the site, no hedge, no other subject
before the anchor (the neighbour/sub-site trap), not the period of a find or of an event. A sentence
that states a year beside the epoch is a year (D101), not a band. D136 re-admits the coarse words
the extractor's `BROAD_PERIODS` holds out, so the candidate run reads with `D136_UNREAD` instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline import periods as P  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, bucket_edge, categorize_period  # noqa: E402

DEFAULT_OUT = REPO / "output" / "remediation" / "fields" / "epoch_bands" / "EPOCH_BANDS.md"


def _year(year: int) -> str:
    return f"{-year} v. Chr." if year < 0 else f"{year} n. Chr."


def other_bands(key: str) -> dict[str, list[str]]:
    """`{band: [countries]}` for the countries whose own start of epoch `key` lies in another band
    than its conventional start; empty for an epoch without regional starts."""
    conventional = P.epoch_band(key, country=None).label
    found: dict[str, list[str]] = {}
    for country in sorted(P.REGIONAL_STARTS.get(key, {})):
        label = P.epoch_band(key, country=country).label
        if label != conventional:
            found.setdefault(label, []).append(country)
    return found


def table() -> str:
    order = {label: i for i, (label, _lo, _hi) in enumerate(PERIOD_BUCKETS)}
    rows = sorted(P.PERIODS.items(), key=lambda item: (item[1][0], item[1][1], item[0]))
    lines = [
        "# Epochen -> Zeitband (D136, aus dem Code erzeugt)",
        "",
        "Erzeugt von `scripts/remediation/fields/epoch_bands.py table` aus "
        "`pipeline.periods.epoch_band` - nicht von Hand ändern.",
        "",
        "Regel: Eine Site mit Epochenwort kommt in das Zeitband, in dem die Epoche **beginnt** "
        "(im Land der Site, wo `REGIONAL_STARTS` einen Landeswert hat, sonst beim üblichen Beginn "
        "aus `PERIODS`). Gespeichert wird die Kante des Bandes (`bucket_edge`, wie bei den 511 "
        "Band-Zeilen vom 04.10.).",
        "",
        f"{len(rows)} Epochen.",
        "",
        "| Epoche | Zeitraum | Zeitband | gespeichertes Jahr | endet in | Länder mit anderem Band |",
        "|---|---|---|---|---|---|",
    ]
    for key, (start, end) in rows:
        band = P.epoch_band(key, country=None)
        others = other_bands(key)
        other_text = "; ".join(
            f"{label}: {', '.join(countries)}"
            for label, countries in sorted(others.items(), key=lambda kv: order[kv[0]])
        )
        lines.append(
            f"| {key} | {_year(start)} – {_year(end)} | {band.label} | {band.edge} | "
            f"{categorize_period(end)} | {other_text} |"
        )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ the candidates
FIELDS_DIR = REPO / "output" / "remediation" / "fields"
HARVEST = FIELDS_DIR / "wd5x" / "harvest"
#: The vocabulary names a D136 candidate does not read as an epoch: `historic` (AD 1000-1800, the
#: word of "State Historic Park") and `classical` (the Greek Classical period, and every other sense
#: of the word). Every other name is read, the coarse ones included (D136).
D136_UNREAD = frozenset({"historic", "classical"})
#: The order of D136's task: the first kind that names an epoch decides.
KINDS = ("lane-quote", "wikidata-p2348", "name", "site-type", "enwiki-lead")
#: The run directories whose quotes are not lane answers: the extractor's own unverified quotes.
_NOT_LANE_QUOTES = ("epoch_bands", "report-615")
_PERIOD_DETAIL = re.compile(r"^period '(?P<key>[^']+)'")
#: A period word that names another thing, not the site's epoch (measured on the first two
#: candidate runs, 2026-11-07): it heads a proper name - a trail ("the Viking Way"), a peninsula
#: ("the Iberian Peninsula"), a road that cut the site ("a Roman Road"), a route of today ("Roman
#: Emperors Route"), a traditional name ("Roman Rig", an earthwork of debated date), a place
#: ("Chavin de Huantar District") - or a thing beside the site ("the old Roman tunnel", "a Roman
#: route map", "the Roman occupation of Britain"), or it labels a language ("(Hittite: ...)").
_HEADS_A_NAME = frozenset({"Way", "Peninsula", "Road", "Route", "Emperors", "Rig"})
_OTHER_THING = frozenset({"tunnel", "route", "map", "occupation", "army", "emperors", "de", "del"})
#: The single-word names that are ordinary English words when written small: "geometric shapes".
_CAPITAL_ONLY = frozenset({"geometric"})
#: Statements that put the epoch in doubt, beyond the extractor's `HEDGES`: "the suggestion that
#: the site originates in the Iron Age is currently unproven", "the date of construction is not
#: certainly known", "it has also been claimed".
#: D137 (the year route): "dated tentatively", "prompted debate over whether", "remains debated",
#: "has not yet been dated with certainty".
_DOUBT = re.compile(r"\b(?:unproven|not certainly known|is not known|been claimed|is uncertain|"
                    r"tentative(?:ly)?|debated?|not (?:yet )?(?:been )?dated with certainty)\b",
                    re.IGNORECASE)  # fmt: skip


def names_another_thing(text: str, key: str) -> bool:
    """Whether every mention of the epoch `key` in `text` names another thing (see above)."""
    words = r"[\s-]+".join(re.escape(w) for w in key.split())
    hits = list(re.finditer(rf"(?i:\b{words})\b(?P<next>:|\s+[\w'’]+)?", text))
    if not hits:
        return False
    if key in _CAPITAL_ONLY and not any(h.group(0)[:1].isupper() for h in hits):
        return True

    def other(h: re.Match[str]) -> bool:
        nxt = (h.group("next") or "").strip()
        return nxt == ":" or nxt in _HEADS_A_NAME or nxt.casefold() in _OTHER_THING

    return all(other(h) for h in hits)


def _mentions(text: str, key: str) -> list[re.Match[str]]:
    words = r"[\s-]+".join(re.escape(w) for w in key.removesuffix(" period").split())
    return list(re.finditer(rf"(?i:\b{words})\b", text))


# ------------------------------------------------- D137: the reading errors of the spot checks
#: Finds of the surroundings, not of the site (Sotin: "finds speak of life in the Sotin area from
#: the Copper Age"): an epoch named after finds, traces or life "in the area", with no name of the
#: site between the place phrase and the epoch ("finds in the area show that Plataea existed from
#: Mycenaean times" dates Plataea; "rock art in the Trialeti area" says where the site lies).
_TRACES = re.compile(
    r"\b(?:finds?|traces?|evidence|life|settlement|habitation|occupation|activity|remains|"
    r"artefacts?|artifacts?|inhabited|settled)\b",
    re.IGNORECASE,
)
_AREA = re.compile(
    r"\b(?:in|around|of|from|throughout|across|within)\s+(?:the\s+)?(?:[\w'’-]+\s+){0,3}?"
    r"(?:area|surroundings|vicinity|environs|neighbou?rhood)\b",
    re.IGNORECASE,
)
#: A feature next to the site (Berry Camp: "an adjoining prehistoric field system"): an epoch
#: right after a word of nearness, an article and one word between at most.
_BESIDE = re.compile(
    r"\b(?:adjoining|adjacent(?:\s+to)?|neighbou?ring|nearby|near(?:\s+to)?|next\s+to|beside|"
    r"close\s+to|surrounding)\s+(?:(?:the|an?|its)\s+)?(?:[\w'’-]+\s+)?\Z",
    re.IGNORECASE,
)
#: A later phase of the site ("reoccupied in the Roman period"): an epoch named after a word of
#: renewal or reuse in the same sentence.
_RENEWAL = re.compile(
    r"\b(?:renew\w*|re-?occup\w*|re-?us(?:e|ed|ing)|rebuil[td]|refortif\w*|restor\w*|"
    r"renovat\w*|reconstruct\w*)\b",
    re.IGNORECASE,
)
#: The site itself called renewed or reused, the sentence naming it (Dolno Gradište).
_RENEWED = re.compile(r"\b(?:renewed|re-?occupied|re-?used|refortified)\b", re.IGNORECASE)
_THE_SITE = re.compile(r"\bthe (?:site|settlement|fort|fortress|hillfort)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _names_a_form(text: str, forms: list[str] | tuple[str, ...]) -> bool:
    norm = f" {P.fold_name(text)} "
    return any(f" {f} " in norm for f in (P.fold_name(x) for x in forms if x) if f)


def sentence_veto(
    sentence: str, key: str, *, forms: list[str] | tuple[str, ...] = ()
) -> str | None:
    """Why every mention of the epoch `key` in `sentence` is not the site's start (D137), or None
    when one mention is: `area` (it dates finds of the surroundings), `beside` (a feature next to
    the site), `renewal` (a later renewal or reuse). `forms` are the names of the site."""
    reasons = []
    for hit in _mentions(sentence, key):
        before = sentence[: hit.start()]
        area = _AREA.search(before)
        if (
            area is not None
            and _TRACES.search(before[: area.start()])
            and not _names_a_form(before[area.end() :], forms)
        ):
            reasons.append("area")
        elif _BESIDE.search(before):
            reasons.append("beside")
        elif _RENEWAL.search(before):
            reasons.append("renewal")
        else:
            return None
    return reasons[0] if reasons else None


#: A year of a find, not of the site ("Material dating from the 1st and 2nd century CE has been
#: found at the site", Burfa Castle).
_FIND_NOUN = re.compile(
    r"\b(?:material|finds?|coins?|pottery|sherds?|artefacts?|artifacts?|objects?|hoards?|"
    r"jewel(?:le)?ry|tools?)\b",
    re.IGNORECASE,
)
_FOUND = re.compile(r"\b(?:found|discovered|unearthed|recovered|hoards?)\b", re.IGNORECASE)
#: The year of a site's end or of its latest phase ("The last stela erected in Sacul bears a date
#: corresponding to AD 800").
_LAST = re.compile(r"\b(?:last|latest|final)\b", re.IGNORECASE)
_NEAR_WORDS = r"(?:below|beneath|beside|near|next to|adjoining|adjacent to|close to|nestled below)"


def year_veto(sentence: str, forms: list[str] | tuple[str, ...]) -> str | None:
    """Why the years `sentence` states are not the site's own (D137), or None: `find` (the year of
    a find at the site), `later-event` (its last or latest phase), `neighbour` (a feature below or
    beside the site: "Nestled below Caer y Twr is a group of huts")."""
    if _FIND_NOUN.search(sentence) and _FOUND.search(sentence):
        return "find"
    if _LAST.search(sentence):
        return "later-event"
    for form in forms:
        if form and re.search(rf"(?i)\b{_NEAR_WORDS}\s+(?:the\s+)?{re.escape(form)}\b", sentence):
            return "neighbour"
    return None


def is_a_measure(sentence: str, year: int) -> bool:
    """Whether the number the reader took for `year` is a measure in `sentence` ("a 160-metre cliff
    castle")."""
    unit = (
        r"(?:metres?|meters?|m|ft|feet|foot|km|kilometres?|kilometers?|miles?|yards?|hectares?|ha)"
    )
    return re.search(rf"(?i)\b{abs(year)}[\s-]*{unit}\b", sentence) is not None


#: A century the sentence gives the site itself, as an attribute ("The Early Roman House is a
#: 1st-century AD residential structure"): the D70 reader takes a year only beside a start cue.
_ATTRIBUTIVE = re.compile(
    r"\b(?:is|was|are|were)\s+(?:an?|the)\s+(?P<n>\d{1,2})(?:st|nd|rd|th)[\s-]+century"
    r"(?:[\s-]+(?P<era>AD|CE|BC|BCE|B\.C\.|A\.D\.))?(?![\w-])",
    re.IGNORECASE,
)


def attributive_century(sentence: str) -> int | None:
    """The start year of the century `sentence` calls the site ("is a 1st-century AD structure" ->
    1, "was a 3rd-century BC temple" -> -300, the D70 convention), or None."""
    found = _ATTRIBUTIVE.search(sentence)
    if found is None:
        return None
    number = int(found.group("n"))
    if (found.group("era") or "").upper().replace(".", "") in {"BC", "BCE"}:
        return -number * 100
    return number * 100 - 99


def renewed_site(texts: list[str], forms: list[str]) -> bool:
    """Whether the site's own text calls the site renewed or reused (a sentence naming it by one of
    its `forms` or as "the site"): its Wikidata period of use (P2348) is then a later phase, not its
    start (D137, Dolno Gradište)."""
    folded = [f for f in (P.fold_name(f) for f in forms if f) if f]
    for text in texts:
        for sentence in _SENTENCE_END.split(text):
            if not _RENEWED.search(sentence):
                continue
            norm = f" {P.fold_name(sentence)} "
            if _THE_SITE.search(sentence) or any(f" {f} " in norm for f in folded):
                return True
    return False


def name_veto(key: str, texts: list[str], *, hedged: Callable[[str], bool]) -> str | None:
    """Why the epoch `key` the site's NAME carries is not its start (D137), or None: `older-or-later`
    when the site's own text puts the site before or after it ("important in pre-Inca times"),
    `hedged` when every sentence of its own text that names the epoch hedges it (the only source of
    Bomarzo: "believed to have served as an Etruscan altar"). A name its texts never mention keeps
    its epoch."""
    words = r"[\s-]+".join(re.escape(w) for w in key.removesuffix(" period").split())
    other_time = re.compile(
        rf"(?i)\b(?:pre|post)[\s-]*{words}\b|\b(?:before|after)\s+the\s+{words}\b"
    )
    if any(other_time.search(t) for t in texts):
        return "older-or-later"
    naming = [s for t in texts for s in _SENTENCE_END.split(t) if _mentions(s, key)]
    if naming and all(hedged(s) for s in naming):
        return "hedged"
    return None


def is_late(sentence: str, key: str) -> bool:
    """Whether `sentence` names "the late <epoch>" for an epoch whose late phase the vocabulary
    holds no key of (La Ribera de Algaida: "the late Copper Age")."""
    if f"late {key}" in P.PERIODS:
        return False
    words = r"[\s-]+".join(re.escape(w) for w in key.removesuffix(" period").split())
    return re.search(rf"(?i)\blate[\s-]+{words}\b", sentence) is not None


def stated_start(year_rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """The year the site's own source states for it that wins over the start of the epoch `key`
    (D137): the earliest stated year that is not after the epoch's end - a year after it is a later
    event of the site ("occupied until the 5th century"), not its start. None without one."""
    end = P.period_of(key)[1]
    found = [(y, row) for row in year_rows for y in row["years"] if y <= end]
    if not found:
        return None
    year, row = min(found, key=lambda f: f[0])
    return {"year": year, "year_quote": row["sentence"], "year_url": row.get("url")}


def option(key: str, site: dict[str, Any], sentence: str) -> dict[str, Any]:
    """The band the epoch `key` of one sentence gives the site (D136 with D137): a coarse word
    (`TYPED_COARSE`) takes the epoch of the site's own monument type (its site_type, its name or the
    same sentence), and a "late" phase the band of the epoch's end."""
    extra: dict[str, Any] = {}
    epoch = key
    if key in P.TYPED_COARSE:
        typed = P.monument_epoch(site.get("site_type"), site.get("name"), sentence)
        if typed is not None:
            extra = {"coarse_word": key, "type_word": typed[0]}
            epoch = typed[1]
    country = site.get("country")
    if is_late(sentence, epoch):
        band = P.late_band(epoch, country=country)
        extra["late"] = True
    else:
        band = P.epoch_band(epoch, country=country)
    return {"epoch": epoch, "band": band.label, "edge": band.edge, "start": band.start,
            "regional": band.regional, **extra}  # fmt: skip


def shares_a_word(title: str, name: str) -> bool:
    """Whether a cached article's `title` shares a word of four letters or more with the site's
    stored `name`: a generic article cached for the site ("Hillfort" for Dinas Dinlle) does not."""

    def words(text: str) -> set[str]:
        return {w for w in P.fold_name(text).split() if len(w) >= 4}

    return bool(words(title) & words(name))


def _lane_quotes(fields_dir: Path, ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """`{site_id: [{quote, url, file, model}]}`: every verbatim quote an earlier lane's period_start
    answer cited and the code found on the page (`outcome: found`), and the quotes of the D113
    conflict list; deduplicated per site."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()

    def add(site_id: str, quote: str, url: str, file: str, model: Any) -> None:
        if site_id in ids and quote and (site_id, quote, url) not in seen:
            seen.add((site_id, quote, url))
            out[site_id].append({"quote": quote, "url": url, "file": file, "model": model})

    files = sorted([*fields_dir.rglob("ATTEMPTS.jsonl"), *fields_dir.rglob("DECISIONS.jsonl")])
    for path in files:
        if any(part in path.parts for part in _NOT_LANE_QUOTES):
            continue
        rel = path.relative_to(REPO).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            for rec in (record, (record.get("adversarial") or {}).get("original") or {}):
                if rec.get("field") != "period_start" or rec.get("site_id") not in ids:
                    continue
                for q in rec.get("quotes") or []:
                    if isinstance(q, dict) and q.get("outcome") == "found":
                        add(rec["site_id"], str(q.get("quote") or ""), str(q.get("source") or ""),
                            rel, rec.get("model"))  # fmt: skip
    conflicts = fields_dir / "D113_CONFLICT_LIST.jsonl"
    for line in conflicts.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for q in row.get("quotes") or []:
            add(row["site_id"], str(q.get("quote") or ""), str(q.get("url") or ""),
                conflicts.relative_to(REPO).as_posix(), row.get("origin"))  # fmt: skip
    return out


class _Reader:
    """The D70 extractor's sentence reading (`fields.dating`), with D136's vocabulary."""

    def __init__(self) -> None:
        remediation = str(REPO / "scripts" / "remediation")
        if remediation not in sys.path:
            sys.path.insert(0, remediation)
        from fields import dating, harvest, wiki

        self.D, self.H = dating, harvest
        self.wiki = wiki.WikiCache(wiki.WIKI_CACHE)
        self.item_labels = json.loads((HARVEST / harvest.ITEM_LABELS_FILE).read_text("utf-8"))
        self.sites = {s["site_id"]: s for s in harvest.read_sites(HARVEST)}
        #: the sentence vetoes (`sentence_veto`) of the site being read, reset per site
        self.vetoed: list[dict[str, Any]] = []

    def hedged(self, sentence: str) -> bool:
        """Whether the D70 extractor reads `sentence` as hedged (`dating.HEDGES`)."""
        return bool(self.D.HEDGES.search(self.D.D.reading_text(sentence).casefold()))

    def forms(self, site: dict[str, Any], entity: dict[str, Any]) -> list[str]:
        """The names a sentence may name the site by, as `dating._Loaded.found` builds them."""
        names = [site["name"], site.get("enwiki_title")]
        for block in ("labels", "aliases"):
            for value in (entity.get(block) or {}).values():
                for item in value if isinstance(value, list) else [value]:
                    names.append(item.get("value"))
        return [f for f in self.D.name_forms(names) if not self.D.is_period_name(f)]

    def mentions(self, text: str, forms: list[str]) -> list[str]:
        """The epochs `text` names (`dating._period_mentions`), less `D136_UNREAD`."""
        found = [key for key, _a, _b in self.D._period_mentions(text, forms)]
        return [
            key for key in found if key not in D136_UNREAD and not names_another_thing(text, key)
        ]

    def sentences(
        self, text: str, *, forms: list[str], url: str, context_named: bool
    ) -> list[dict[str, Any]]:
        """Each sentence of `text` that names an epoch of the site or states a year of it."""
        D = self.D
        out: list[dict[str, Any]] = []
        named = context_named
        for sentence in D.split_sentences(text):
            found = D.sentence_candidates(sentence, lang="en", forms=forms, context_named=named,
                                          tier=0, source="d136", url=url, revision=None,
                                          sentence_id=url)  # fmt: skip
            epochs: list[str] = []
            for c in found.candidates:
                match = _PERIOD_DETAIL.match(c.detail)
                key = match.group("key") if match else None
                if c.kind == D.PERIOD and key and key not in D136_UNREAD:
                    if not names_another_thing(sentence, key):
                        epochs.append(key)
            if _DOUBT.search(sentence):
                continue
            years = [c.start for c in found.candidates
                     if c.kind != D.PERIOD and not is_a_measure(sentence, c.start)]  # fmt: skip
            if not years and (named or D.names_site(sentence, forms)) and not self.hedged(sentence):
                century = attributive_century(sentence)
                years = [] if century is None else [century]
            if years and year_veto(sentence, forms) is not None:
                years = []
            several = any(n.reason == D.SEVERAL_PERIODS for n in found.notes)
            if several:  # anchored and unhedged; the site's history, which begins at its first
                epochs = [k for k in self.mentions(sentence, forms)
                          if not D.FINDS.match(D.D.reading_text(sentence).casefold(),
                                               self._end(sentence, k))]  # fmt: skip
            vetoed = {k: why for k in epochs
                      if (why := sentence_veto(sentence, k, forms=forms)) is not None}  # fmt: skip
            epochs = [k for k in epochs if k not in vetoed]
            if epochs or years:
                out.append({"sentence": sentence, "epochs": epochs, "years": years,
                            "mode": "earliest-of-several" if several else "single"})  # fmt: skip
            if vetoed:
                self.vetoed.append({"sentence": sentence, "vetoed": vetoed, "url": url})
            if D.names_site(sentence, forms):
                named = True
        return out

    def _end(self, sentence: str, key: str) -> int:
        for k, _a, b in self.D._period_mentions(sentence, ()):
            if k == key:
                return b
        return 0


def _band(key: str, country: str | None) -> dict[str, Any]:
    band = P.epoch_band(key, country=country)
    return {"epoch": key, "band": band.label, "edge": band.edge, "start": band.start,
            "regional": band.regional}  # fmt: skip


def site_candidates(
    reader: _Reader,
    site: dict[str, Any],
    quotes: list[dict[str, Any]],
    reset: dict[str, Any] | None,
) -> dict[str, Any]:
    """Every epoch the site's own evidence names, by kind, and the one D136 takes."""
    D, H = reader.D, reader.H
    reader.vetoed = []
    hs = reader.sites[site["id"]]
    qid = hs.get("qid")
    entity = H.load_entity(HARVEST, qid) if qid else {}
    forms = reader.forms(hs, entity)
    country = site.get("country")
    own_pages = {str(site.get("source_url") or "")}
    evidence: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    years: list[dict[str, Any]] = []
    for q in quotes:
        own = q["url"] in own_pages or (
            bool(hs.get("enwiki_title"))
            and q["url"].rstrip("/").endswith("/" + str(hs["enwiki_title"]).replace(" ", "_"))
        )
        for hit in reader.sentences(q["quote"], forms=forms, url=q["url"], context_named=own):
            row = {**hit, "url": q["url"], "file": q["file"], "quoted_by": q["model"]}
            (evidence["lane-quote"] if hit["epochs"] and not hit["years"] else years).append(row)
    own_pages = [
        page for page in reader.wiki.pages(site["id"])
        if not page.get("missing") and page.get("lang") == "en"
        and not D.is_period_name(str(page.get("resolved_title") or page.get("title") or ""))
        and shares_a_word(str(page.get("resolved_title") or page.get("title") or ""), site["name"])
    ]  # fmt: skip
    # the citation markers "[1]." stop `split_sentences` (a number of two digits before a stop)
    description = re.sub(r"\s*\[\d+\]", "", str(site.get("description") or ""))
    own_texts = [q["quote"] for q in quotes] + [description] + [
        " ".join(p for _s, _lead, p in D.readable_paragraphs(str(page["text"]))) for page in own_pages
    ]  # fmt: skip
    kept = list(reader.vetoed)  # the description is read for its years only
    for hit in reader.sentences(description, forms=forms, url="unified_sites.description",
                                context_named=True):  # fmt: skip
        if hit["years"]:
            years.append({**hit, "url": "unified_sites.description", "file": "unified_sites"})
    reader.vetoed = kept
    vetoes: list[dict[str, Any]] = []
    renewed = renewed_site(own_texts, forms)
    for period in D._item_ids(entity, "P2348"):
        label = str((reader.item_labels.get(period) or {}).get("label") or "")
        key = P.fold_name(label)
        if not label or P._key_of(label) is None or P._key_of(label) in D136_UNREAD:
            evidence.setdefault("p2348-unread", []).append({"item": period, "label": label})
            continue
        if renewed:  # D137: the period of use of a site its own text calls renewed
            vetoes.append({"kind": "wikidata-p2348", "epoch": P._key_of(label), "why": "renewal"})
            continue
        evidence["wikidata-p2348"].append({"sentence": f"P2348: {period} ({label})",
                                           "epochs": [P._key_of(label) or key],
                                           "url": D.wikidata_url(qid, entity), "mode": "single"})  # fmt: skip
    for kind, text in (("name", site["name"]), ("site-type", site.get("site_type") or "")):
        epochs = reader.mentions(text, [])
        if kind == "name":
            for key in list(epochs):
                why = name_veto(key, own_texts, hedged=reader.hedged)
                if why is not None:
                    vetoes.append({"kind": kind, "epoch": key, "why": why})
                    epochs.remove(key)
        if epochs:
            evidence[kind].append({"sentence": text, "epochs": epochs, "url": "unified_sites."
                                   + ("name" if kind == "name" else "site_type"),
                                   "mode": "single" if len(epochs) == 1 else "earliest-of-several"})  # fmt: skip
    for page in own_pages:
        title = str(page.get("resolved_title") or page.get("title") or "")
        lead = " ".join(p for _s, is_lead, p in D.readable_paragraphs(str(page["text"])) if is_lead)
        url = D.permalink("en", title, page.get("revid"))
        for hit in reader.sentences(lead, forms=D.name_forms([*forms, title]), url=url,
                                    context_named=False):  # fmt: skip
            row = {**hit, "url": url, "file": "wiki_cache"}
            (evidence["enwiki-lead"] if hit["epochs"] and not hit["years"] else years).append(row)
    chosen = None
    for kind in KINDS:
        rows = [r for r in evidence[kind] if r["epochs"]]
        if not rows:
            continue
        options = [(option(key, site, r["sentence"]), r) for r in rows for key in r["epochs"]]
        best, row = min(options, key=lambda o: (o[0]["start"], o[0]["epoch"]))
        chosen = {"source_kind": kind, **best, "quote": row["sentence"], "url": row["url"],
                  "mode": row["mode"], "file": row.get("file"), "quoted_by": row.get("quoted_by"),
                  "band_from": "epoch"}  # fmt: skip
        stated = stated_start(years, best["epoch"])
        if stated is not None:  # D137: a year the site's own source states wins over the epoch
            label = categorize_period(stated["year"])
            assert label is not None  # a year always has a bucket
            chosen.update(stated, band=label, edge=bucket_edge(label), band_from="year",
                          epoch_band=best["band"])  # fmt: skip
        break
    bands = sorted({_band(k, country)["band"] for kind in KINDS for r in evidence[kind]
                    for k in r["epochs"]})  # fmt: skip
    out: dict[str, Any] = {"site_id": site["id"], "name": site["name"], "country": country,
                           "site_type": site.get("site_type")}  # fmt: skip
    if chosen is None:
        out["status"] = "year-stated-only" if years else "undated"
        if years:
            out["year_band"] = categorize_period(min(y for row in years for y in row["years"]))
    else:
        scope = D.scope_problem({**hs, "country": country}, chosen["edge"])
        out.update(chosen)
        out["status"] = "scope-hold" if scope else "band"
        if scope:
            out["scope"] = scope
    out["bands_seen"] = bands
    out["year_sentences"] = years[:3]
    if vetoes or reader.vetoed:
        out["d137_vetoes"] = vetoes + reader.vetoed
    out["other_kinds"] = {k: [e for r in v for e in r.get("epochs", [])]
                          for k, v in evidence.items() if v and k != out.get("source_kind")}  # fmt: skip
    if reset is not None:
        out["d121_d122_reset"] = reset
    return out


def candidates(sites_file: Path, resets_file: Path, run: Path) -> dict[str, Any]:
    sites = [json.loads(line) for line in sites_file.read_text(encoding="utf-8").splitlines()]
    resets = {}
    for line in resets_file.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rule = next((e["quote"] for e in row["evidence"] if "reasoning" in e.get("source", "")), "")
        resets[row["row_pk"]] = {"old": row["old"], "rule_reason": rule,
                                 "decision": row["evidence"][0]["source"]}  # fmt: skip
    reader = _Reader()
    quotes = _lane_quotes(FIELDS_DIR, {s["id"] for s in sites})
    saved = reader.D.BROAD_PERIODS
    reader.D.BROAD_PERIODS = frozenset()  # D136 reads the coarse words (`D136_UNREAD` aside)
    try:
        rows = [site_candidates(reader, s, quotes.get(s["id"], []), resets.get(s["id"]))
                for s in sites]  # fmt: skip
    finally:
        reader.D.BROAD_PERIODS = saved
    run.mkdir(parents=True, exist_ok=True)
    with (run / "CANDIDATES.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    banded = [r for r in rows if r["status"] == "band"]
    summary = {
        "sites": len(rows),
        "status": dict(Counter(r["status"] for r in rows).most_common()),
        "band": dict(Counter(r["band"] for r in banded).most_common()),
        "source_kind": dict(Counter(r["source_kind"] for r in banded).most_common()),
        "epoch": dict(Counter(r["epoch"] for r in banded).most_common()),
        "regional": dict(Counter(r["regional"] for r in banded).most_common()),
        "mode": dict(Counter(r["mode"] for r in banded).most_common()),
        "band_from": dict(Counter(r["band_from"] for r in banded).most_common()),
        "typed_coarse": dict(
            Counter(
                f"{r['coarse_word']} -> {r['type_word']} ({r['epoch']})"
                for r in banded
                if "type_word" in r
            ).most_common()
        ),
        "late_phase": sum(1 for r in banded if r.get("late")),
        "d137_vetoed_sites": sum(1 for r in rows if "d137_vetoes" in r),
        "several_bands_seen": sum(1 for r in banded if len(r["bands_seen"]) > 1),
        "resets_among_banded": sum(1 for r in banded if "d121_d122_reset" in r),
        "resets_total": sum(1 for r in rows if "d121_d122_reset" in r),
    }
    (run / "SUMMARY.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), "utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("table", help="write EPOCH_BANDS.md from pipeline.periods")
    write.add_argument("--out", type=Path, default=DEFAULT_OUT)
    cand = sub.add_parser("candidates", help="the epoch each undated site's own evidence names")
    cand.add_argument("--sites", type=Path, required=True)
    cand.add_argument("--resets", type=Path, required=True)
    cand.add_argument("--run", type=Path, default=DEFAULT_OUT.parent)
    args = parser.parse_args(argv)
    if args.command == "table":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(table(), encoding="utf-8")
        print(f"wrote {args.out} ({len(P.PERIODS)} epochs)")
    if args.command == "candidates":
        print(json.dumps(candidates(args.sites, args.resets, args.run), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

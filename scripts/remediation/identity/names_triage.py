"""D23: which names are defective, and what would a short spoken name be - by rule alone.

**Triage** (`NAMES_TRIAGE.jsonl`). A shown site's name is defective when it shows one of
`DEFECTS`. Each defect is a plain test on the stored name; `differs_from_label` also needs the
linked item's English label (no word in common with the label or any English alias). The owner's
D23: a broken or foreign name becomes the English name, the old name stays a searchable alias; the
new name must be an attested form of the site's item - its English label, an English alias, or its
English Wikipedia title (the rule `name_fix` and L5 hold). So the triage proposes a
`suggestion` only when the repaired name *is* such a form (`kind` `whitespace`, `homoglyph` or
`attested_form`), and flags everything else `needs_model`.

**Spoken name** (`SPOKEN_RULE.jsonl`). The short name the Short's closing line says: the name
without `, qualifier`, parentheses and trailing numerals, then the shortest attested English form
that is still the same name (`compatible`: at least half of the significant words in common). A name
the rule cannot make clean (a non-Latin letter, a digit, a foreign prefix, a mixed script, a name of
one generic word, longer than `SPOKEN_MAX_CHARS`) is flagged `needs_model` with the reasons; the
model is later constrained to the attested forms listed in the record.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import common, entities, export  # noqa: E402

TRIAGE_OUTPUT = "NAMES_TRIAGE.jsonl"
SPOKEN_OUTPUT = "SPOKEN_RULE.jsonl"

DEFECTS = (
    "nonlatin_script",
    "mixed_script",
    "whitespace_artifact",
    "edge_punctuation",
    "all_caps",
    "mojibake",
    "digit",
    "parenthesis",
    "foreign_prefix",
    "comma_qualifier",
    "long",
)
LONG_NAME_CHARS = 40
SPOKEN_MAX_CHARS = 40
SPOKEN_MIN_CHARS = 3
#: Jaccard overlap of significant words from which two names count as the same name.
COMPATIBLE = 0.5
LABEL_OVERLAP = 0.34

FOREIGN_PREFIX = re.compile(
    r"^(Dolmen d(?:e|el|a|as|os)|Menhir du|Templo|Templos|Tempio|Castillo|Castello|Château|Cueva|"
    r"Cova|Yacimiento|Sitio|Zona|Gruta|Grotta|Necrópolis|Necropoli|Tumba|Torre d(?:e|el|els|')|"
    r"Iglesia|Chiesa|Ermita|Pont|Église|Abbaye|Grotte|Parque|Santuario|Mura|Museo|Teatro|Ruinas|"
    r"Villa Romana)\b"
)
ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
WHITESPACE_ARTIFACT = re.compile(r"[\u200b-\u200f\u2060\ufeff]|\s{2,}|^\s|\s$")
#: A dash, comma, semicolon or colon at the start or the end of a name (a cut-off title).
EDGE_PUNCTUATION = re.compile(r"^[-–—,;:.]|[-–—,;:]$")
MOJIBAKE = re.compile("\ufffd|\u00c3.|\u00e2\u20ac")
PARENTHESIS = re.compile(r"\s*\([^)]*\)")
#: "Tumulus 3", "Cave 12a": an Arabic numeral at the end. A Roman one stays: it is mostly a
#: regnal number ("Tomb of Artaxerxes III"), which is part of the name.
TRAILING_NUMERAL = re.compile(r"\s+\d+[a-z]?\s*$")
#: A name that is only the kind of the thing says nothing once its numeral is gone.
GENERIC = frozenset(
    "dolmen menhir tomb cave church castle fort tumulus mound temple cairn barrow grave site "
    "hillfort villa cemetery necropolis settlement ruins monument stone circle".split()
)
#: The kinds of building a name may be made of with no place in it ("Roman Theatre"), and the
#: foreign adjective of "Villa Romana": a name of nothing else names no site.
BUILDING_KINDS = frozenset(
    "theatre theater amphitheatre amphitheater bridge baths bath aqueduct basilica forum palace "
    "fortress sanctuary mausoleum arch walls wall gate tower lighthouse harbour harbor mine quarry "
    "romana romano romaine romain".split()
)
#: The words a spoken name may leave out: articles and the kind of the thing.
DROPPABLE = common.STOP_TOKENS | GENERIC
#: Latin look-alikes in Greek and Cyrillic (the letters a typist's keyboard swaps).
HOMOGLYPHS = str.maketrans(
    {
        "\u0391": "A",
        "\u0392": "B",
        "\u0395": "E",
        "\u0396": "Z",
        "\u0397": "H",
        "\u0399": "I",
        "\u039a": "K",
        "\u039c": "M",
        "\u039d": "N",
        "\u039f": "O",
        "\u03a1": "P",
        "\u03a4": "T",
        "\u03a5": "Y",
        "\u03a7": "X",
        "\u03bf": "o",
        "\u03bd": "v",
        "\u0410": "A",
        "\u0412": "B",
        "\u0415": "E",
        "\u041a": "K",
        "\u041c": "M",
        "\u041d": "H",
        "\u041e": "O",
        "\u0420": "P",
        "\u0421": "C",
        "\u0422": "T",
        "\u0425": "X",
        "\u0430": "a",
        "\u0435": "e",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0445": "x",
        "\u0443": "y",
        "\u0456": "i",
    }
)


def script_of(char: str) -> str | None:
    """The script word of a letter's Unicode name (`LATIN`, `GREEK`, ...); `None` for a mark,
    a digit, a modifier letter or anything that is not a letter."""
    if not char.isalpha() or unicodedata.category(char) == "Lm":
        return None
    return unicodedata.name(char, "UNKNOWN").split()[0]


def scripts_of(word: str) -> set[str]:
    return {s for s in map(script_of, word) if s}


def is_latin(text: str) -> bool:
    return all(s == "LATIN" for s in map(script_of, text) if s)


def defects_of(name: str) -> list[str]:
    """The defects a stored name shows, each a plain test on the name."""
    found: list[str] = []
    if not is_latin(name):
        found.append("nonlatin_script")
    if any(len(scripts_of(word)) > 1 for word in name.split()):
        found.append("mixed_script")
    if WHITESPACE_ARTIFACT.search(name):
        found.append("whitespace_artifact")
    if EDGE_PUNCTUATION.search(name):
        found.append("edge_punctuation")
    if name.isupper() and len(name) > 3:
        found.append("all_caps")
    if MOJIBAKE.search(name):
        found.append("mojibake")
    if re.search(r"\d", name):
        found.append("digit")
    if re.search(r"\(.*\)", name):
        found.append("parenthesis")
    if FOREIGN_PREFIX.match(name):
        found.append("foreign_prefix")
    if "," in name:
        found.append("comma_qualifier")
    if len(name) > LONG_NAME_CHARS:
        found.append("long")
    return found


def differs_from_label(name: str, label: str | None, english: Sequence[str]) -> bool:
    """The name shares (almost) no word with the item's English label and is none of its English
    forms. Not a defect by itself (1,151 names differ from the label): a note for the judge."""
    if not label:
        return False
    mine, theirs = common.tokens(name), common.tokens(label)
    known = {n.casefold() for n in english}
    return bool(
        mine
        and theirs
        and len(mine & theirs) / len(mine | theirs) < LABEL_OVERLAP
        and name.casefold() not in known
    )


def title_form(title: str) -> str:
    """An English Wikipedia title as a name: underscores to spaces, no `(disambiguator)`."""
    return PARENTHESIS.sub("", title.replace("_", " ")).strip()


def english_forms(aliases: Sequence[str], titles: Sequence[str]) -> list[str]:
    """The English names an item is known by besides its label: its aliases and the titles of
    its English Wikipedia articles. One list for the triage and the spoken records."""
    return [*aliases, *(title_form(t) for t in titles)]


def attested_forms(
    label: str | None,
    aliases: Sequence[str],
    titles: Sequence[str],
    site_names: Sequence[str],
) -> list[tuple[str, str]]:
    """`(form, source)` pairs, deduplicated by case-folded form, the label first."""
    forms: list[tuple[str, str]] = []
    seen: set[str] = set()
    candidates = (
        [(label, "label")] if label else [],
        [(a, "alias") for a in aliases],
        [(title_form(t), "enwiki_title") for t in titles],
        [(n, "site_label") for n in site_names],
    )
    for group in candidates:
        for form, source in group:
            if form and form.casefold() not in seen:
                seen.add(form.casefold())
                forms.append((form, source))
    return forms


def collapse(name: str) -> str:
    return re.sub(r"\s+", " ", ZERO_WIDTH.sub("", name)).strip()


def drop_qualifiers(name: str) -> str:
    """The name without `(parentheses)` and without everything after its first comma."""
    return PARENTHESIS.sub("", name).split(",")[0].strip()


def suggestion(name: str, forms: Sequence[tuple[str, str]]) -> dict[str, Any] | None:
    """A repair of the name that is itself an attested form, or `None`."""
    attested = {form.casefold(): (form, source) for form, source in forms}
    steps = (
        ("whitespace", collapse(name)),
        ("homoglyph", collapse(name).translate(HOMOGLYPHS)),
        ("attested_form", collapse(drop_qualifiers(name).translate(HOMOGLYPHS))),
    )
    for kind, repaired in steps:
        if repaired and repaired != name and is_latin(repaired) and repaired.casefold() in attested:
            form, source = attested[repaired.casefold()]
            return {"kind": kind, "value": form, "source": source}
    return None


def triage_record(
    row: Mapping[str, Any], label: str | None, aliases: Sequence[str], titles: Sequence[str]
) -> dict[str, Any] | None:
    name = row["name"]
    found = defects_of(name)
    if not found:
        return None
    forms = attested_forms(label, aliases, titles, [])
    repair = suggestion(name, forms)
    return {
        "id": row["id"],
        "name": name,
        "country": row["country"],
        "site_type": row["site_type"],
        "defects": found,
        "differs_from_label": differs_from_label(name, label, english_forms(aliases, titles)),
        "severity": "comma_only" if found == ["comma_qualifier"] else "hard",
        "label": label,
        "aliases": list(aliases)[:12],
        "enwiki": list(titles),
        "suggestion": repair,
        "needs_model": repair is None,
    }


def identifying_words(text: str) -> list[str]:
    """The words of a name that are neither an article, the kind of the thing nor a kind of
    building, and longer than one letter: what is left to tell this site from any other."""
    return [
        w
        for w in re.findall(r"[^\W\d_]+", text)
        if len(w) > 1
        and common.fold(w).strip() not in common.STOP_TOKENS | GENERIC | BUILDING_KINDS
    ]


def residual_defects(text: str) -> list[str]:
    """What is still wrong with a name the rule has already shortened (the reasons it cannot be
    spoken by rule)."""
    reasons: list[str] = []
    if not is_latin(text):
        reasons.append("nonlatin_script")
    if any(len(scripts_of(word)) > 1 for word in text.split()):
        reasons.append("mixed_script")
    if re.search(r"\d", text):
        reasons.append("digit")
    if FOREIGN_PREFIX.match(text):
        reasons.append("foreign_prefix")
    if len(text) > SPOKEN_MAX_CHARS:
        reasons.append("too_long")
    if len(text) < SPOKEN_MIN_CHARS:
        reasons.append("too_short")
    if not identifying_words(text):
        reasons.append("generic_only")
    if text.isupper() and len(text) > SPOKEN_MIN_CHARS:
        reasons.append("all_caps")
    return reasons


def compatible(name: str, form: str) -> bool:
    """`form` can stand for `name`: at least half of their significant words are shared and the
    name's most distinctive word (its longest that is not the kind of the thing) is in the form."""
    left, right = common.tokens(name), common.tokens(form)
    if not left or not right or len(left & right) / len(left | right) < COMPATIBLE:
        return False
    return max(left - GENERIC or left, key=lambda t: (len(t), t)) in right


def shortens(name: str, form: str) -> bool:
    """`form` is the name with only droppable words left out and none added (accents and case
    ignored): articles and kinds ("The", "Archaeological Site", "Hill Fort"), never a place."""
    kept, original = common.fold(form).split(), common.fold(name).split()
    dropped = set(original) - set(kept)
    return bool(kept) and bool(dropped) and set(kept) <= set(original) and dropped <= DROPPABLE


def cleaned_name(name: str) -> tuple[str, list[str]]:
    """The name without its whitespace artifacts, qualifiers, trailing numeral and edge dashes,
    and the steps that took."""
    steps: list[str] = []
    text = collapse(name)
    if text != name:
        steps.append("whitespace")
    stripped = drop_qualifiers(text)
    if stripped != text:
        steps.append("qualifier")
    numberless = TRAILING_NUMERAL.sub("", stripped).strip()
    if numberless != stripped:
        steps.append("numeral")
    trimmed = numberless.strip(" -–—")
    if trimmed != numberless:
        steps.append("punctuation")
    return trimmed, steps


def spoken_record(row: Mapping[str, Any], forms: Sequence[tuple[str, str]]) -> dict[str, Any]:
    name = row["name"]
    cleaned, steps = cleaned_name(name)
    reasons = residual_defects(cleaned) if cleaned else ["empty"]
    options: list[tuple[str, str]] = []
    clean = bool(cleaned) and not reasons
    if clean:
        options.append((cleaned, "name"))
    for form, source in forms:
        if form == cleaned or residual_defects(form):
            continue
        if shortens(cleaned, form) if clean else compatible(cleaned or name, form):
            options.append((form, source))
    chosen: tuple[str, str] | None = None
    if options:
        chosen = min(options, key=lambda o: (len(o[0]), 0 if o[1] == "name" else 1, o[0]))
    return {
        "id": row["id"],
        "name": name,
        "country": row["country"],
        "has_description": row["description_chars"] > 0,
        "spoken": chosen[0] if chosen else None,
        "source": chosen[1] if chosen else None,
        "steps": steps,
        "needs_model": chosen is None,
        "reasons": reasons,
        "attested": [f for f, _ in forms],
    }


def mark_ambiguous(spoken: list[dict[str, Any]], rows: Sequence[Mapping[str, Any]]) -> int:
    """A name spoken by rule after its qualifier was dropped that another shown site's cleaned
    name equals ("Temple of Apollo" from Delphi and from Pompeii) no longer says which site: it
    goes to the model with the reason `ambiguous_after_qualifier`. Returns how many."""
    held = Counter(cleaned_name(r["name"])[0].casefold() for r in rows)
    marked = 0
    for record in spoken:
        if (
            "qualifier" in record["steps"]
            and record["source"] == "name"
            and held[record["spoken"].casefold()] > 1
        ):
            record.update(
                spoken=None,
                source=None,
                needs_model=True,
                reasons=[*record["reasons"], "ambiguous_after_qualifier"],
            )
            marked += 1
    return marked


def build(
    exported: export.Export, store: entities.EntityStore
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    qids = export.qids_by_site(exported.ext_ids)
    enwiki = export.enwiki_by_site(exported.ext_ids)
    english: dict[str, list[str]] = defaultdict(list)
    own_label: dict[str, list[str]] = defaultdict(list)
    for entry in exported.names:
        if entry["name_type"] == "label":
            own_label[entry["site_id"]].append(entry["name"])
        else:
            english[entry["site_id"]].append(entry["name"])

    triage: list[dict[str, Any]] = []
    spoken: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in exported.shown:
        site_id = row["id"]
        label: str | None = None
        aliases: list[str] = list(english.get(site_id, []))
        for qid in qids.get(site_id, []):
            entity, _ = store.get(qid)
            if entity is None:
                counts["entity_missing"] += 1
                continue
            label = label or entities.en_label(entity)
            aliases.extend(entities.en_aliases(entity))
        aliases = list(dict.fromkeys(aliases))
        titles = enwiki.get(site_id, [])
        record = triage_record(row, label, aliases, titles)
        if record is not None:
            triage.append(record)
            counts["defective"] += 1
            counts["defective_needs_model"] += record["needs_model"]
            counts["defective_suggested"] += not record["needs_model"]
            counts["comma_only"] += record["severity"] == "comma_only"
            for defect in record["defects"]:
                counts["defect_" + defect] += 1
        forms = attested_forms(label, aliases, titles, own_label.get(site_id, []))
        said = spoken_record(row, forms)
        said["differs_from_label"] = differs_from_label(
            row["name"], label, english_forms(aliases, titles)
        )
        spoken.append(said)
    counts["spoken_ambiguous"] = mark_ambiguous(spoken, exported.shown)
    for said in spoken:
        counts["differs_from_label_note"] += said["differs_from_label"]
        counts["spoken_by_rule"] += not said["needs_model"]
        counts["spoken_needs_model"] += said["needs_model"]
        counts["spoken_changed"] += (not said["needs_model"]) and said["spoken"] != said["name"]
    triage.sort(key=lambda r: (r["severity"] != "hard", r["name"].casefold(), r["id"]))
    spoken.sort(key=lambda r: r["id"])
    counts["shown"] = len(exported.shown)
    return triage, spoken, dict(sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D23 name triage and rule-made spoken names.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    args = parser.parse_args(argv)
    run = common.run_dir(args.root)
    exported = export.load_export(run / common.EXPORT_FILE)
    triage, spoken, counts = build(exported, entities.default_store(args.root))
    common.write_jsonl(run / TRIAGE_OUTPUT, triage)
    common.write_jsonl(run / SPOKEN_OUTPUT, spoken)
    common.record_counts(run, "names_triage", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

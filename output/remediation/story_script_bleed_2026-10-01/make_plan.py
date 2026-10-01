"""Correction plan for the six stories that carry a foreign script (2026-10-01).

Reads before.json (the rows as production holds them, fetched read-only) and
writes, next to it: after.json, DIFF.txt, APPLY.sql and ROLLBACK.sql.
Nothing here touches the database.

Five rows get a minimal, evidence-backed replacement of the foreign fragment.
Story 6266 was written entirely in Chinese by the model and is rewritten in
English from the transcript segment of its video (QFPQ7jtLgB0, 17:10-20:35).

Every replacement must hit at least once, and every resulting text must pass
the same detector the Lyra steps now use (story_script_bleed).

    ./.venv/Scripts/python.exe output/remediation/story_script_bleed_2026-10-01/make_plan.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pipeline.lyra.story_language import story_script_bleed  # noqa: E402
from pipeline.utils.slugs import story_slug  # noqa: E402

HERE = Path(__file__).parent

#: id -> [(old fragment, new fragment, why)]
REPLACEMENTS: dict[int, list[tuple[str, str, str]]] = {
    8351: [
        (
            "Локалитет Беловоде код Петровца на Млави",
            "Belovode",
            "Serbian-Cyrillic name of the locality; the pipeline's own site_name_extracted "
            "for this item is 'Belovode', and the story already writes 'Pločnik' in Latin.",
        )
    ],
    8359: [
        (
            "大汶口遗址公园",
            "Dawenkou",
            "Chinese name of the Dawenkou site; the pipeline's own site_name_extracted is "
            "'Dawenkou', and the post's '4,300-2,600 BCE' is the Dawenkou culture.",
        )
    ],
    6342: [
        (
            "vs人工 structure",
            "vs man-made structure",
            "人工 means man-made; the facts of the same item say 'natural or constructed'.",
        )
    ],
    5733: [
        (
            "Researchers科尔 Chromemer",
            "Researchers Cole Chromemer",
            "科尔 is 'Cole'; the transcript segment of this item reads 'As Cole Chromemer and'.",
        )
    ],
    5797: [
        (
            "have存在的问题",
            "have problems",
            "存在的问题 means 'existing problems'; the sentence is 'dating methods have problems'. "
            "This story is withdrawn (significance 1); the text is fixed for consistency.",
        )
    ],
}

# Story 6266: headline, facts, summary and post were all Chinese. Rewritten from
# the host's argument in the transcript (QFPQ7jtLgB0, 17:10-20:35); no claim
# beyond it. The Chinese original said "no precision machining in the 1960s";
# the host says maybe, "but it would take an incredibly talented craftsman", so
# that overstatement is not carried over.
HEADLINE_6266 = "Precision stone vases as modern fakes? Host argues cost, tooling and provenance say no"
FACTS_6266 = [
    "Making the vases as they are today would take five-axis CNC machines grinding granite, at very high cost",
    "Plain stone vases were worth little on the 1960s to 1980s antiquities market, so such costly forgery would not pay",
    "A forger working for profit could have turned out imprecise copies from an ordinary lathe shop, and nobody was doing precision metrology on the vases until recently",
    "The vases show subtle mathematical design and a radial traversal pattern",
    "Lug-handled vases have complex geometry that cannot be made on a lathe alone; the host says evidence suggests a machine with five axes of freedom",
    "Even the least provenanced vases have histories back to the 1980s or the 1960s, before computer-controlled five-axis mills",
]
POST_6266 = (
    "The host argues that calling these precision stone vases modern forgeries makes little sense. "
    "Reproducing them today would take five-axis CNC machines grinding granite at great cost, while plain "
    "stone vases were worth little on the 1960s to 1980s antiquities market. A forger after profit could have "
    "turned out imprecise copies on a lathe. Even the least documented vases have histories back to the 1980s "
    "or the 1960s, before computer-controlled five-axis mills, and the lug-handled forms have geometry a lathe "
    "alone cannot produce."
)


def compose_summary(headline: str, facts: list[str]) -> str:
    """Exactly how pipeline/lyra/summarizer.py builds it: headline + the first three facts."""
    return " ".join([f"{headline}.", *[f.strip() for f in facts[:3]]])


def replace_everywhere(row: dict, pairs: list[tuple[str, str, str]]) -> dict:
    out = {k: row[k] for k in ("headline", "summary", "post_text", "facts")}
    for old, new, _why in pairs:
        hits = 0
        for field in ("headline", "summary", "post_text"):
            hits += out[field].count(old)
            out[field] = out[field].replace(old, new)
        facts = []
        for fact in out["facts"]:
            hits += fact.count(old)
            facts.append(fact.replace(old, new))
        out["facts"] = facts
        if hits == 0:
            raise SystemExit(f"story {row['id']}: {old!r} not found: the row changed since before.json")
    return out


def put(path: Path, text: str) -> None:
    """Write bytes, not text: on Windows write_text turns every \\n into \\r\\n, and the SQL
    files carry story text with line breaks inside their literals. A guard that compares
    against such a literal then never matches (found on story 6342), and an UPDATE would
    have stored the \\r\\n."""
    path.write_bytes(text.encode("utf8"))


def dq(text: str, tag: str) -> str:
    """A dollar-quoted SQL literal; the tag must not occur in the text."""
    if f"${tag}$" in text:
        raise SystemExit(f"dollar-quote tag {tag} occurs in the text")
    return f"${tag}${text}${tag}$"


def update_sql(story_id: int, old: dict, new: dict) -> str:
    """UPDATE ... WHERE id AND every old value still as expected; the DO block checks exactly one row."""
    literals = {
        "headline": lambda v: dq(v, "nh"),
        "summary": lambda v: dq(v, "ns"),
        "post_text": lambda v: dq(v, "np"),
        "facts": lambda v: dq(json.dumps(v, ensure_ascii=False), "nf") + "::jsonb",
    }
    # Only what changes is written; the guard below still pins all four old values.
    sets = ", ".join(f"{col} = {lit(new[col])}" for col, lit in literals.items() if old[col] != new[col])
    guard = " AND ".join(
        [
            f"id = {story_id}",
            f"headline = {dq(old['headline'], 'oh')}",
            f"summary = {dq(old['summary'], 'os')}",
            f"post_text = {dq(old['post_text'], 'op')}",
            f"facts = {dq(json.dumps(old['facts'], ensure_ascii=False), 'of')}::jsonb",
        ]
    )
    return (
        f"  UPDATE news_items SET {sets} WHERE {guard};\n"
        f"  GET DIAGNOSTICS n = ROW_COUNT;\n"
        f"  IF n <> 1 THEN RAISE EXCEPTION 'story {story_id}: % rows updated, expected 1', n; END IF;\n"
    )


def check_sql(title: str, pairs: list[tuple[int, dict]]) -> str:
    """Read-only: how many rows match each expected row. Every count must be 1."""
    selects = "\nUNION ALL\n".join(
        f"SELECT {i} AS id, count(*) AS matching_rows FROM news_items WHERE "
        + " AND ".join(
            [
                f"id = {i}",
                f"headline = {dq(row['headline'], 'ch')}",
                f"summary = {dq(row['summary'], 'cs')}",
                f"post_text = {dq(row['post_text'], 'cp')}",
                f"facts = {dq(json.dumps(row['facts'], ensure_ascii=False), 'cf')}::jsonb",
            ]
        )
        for i, row in pairs
    )
    return f"-- {title}\n-- Read-only SELECT. Every matching_rows must be 1.\n{selects}\nORDER BY id;\n"


def script(title: str, pairs: list[tuple[int, dict, dict]]) -> str:
    body = "".join(update_sql(i, old, new) for i, old, new in pairs)
    return (
        f"-- {title}\n-- One transaction; every UPDATE is guarded by the full previous value of the row.\n"
        "BEGIN;\nDO $apply$\nDECLARE n integer;\nBEGIN\n" + body + "END\n$apply$;\nCOMMIT;\n"
    )


def main() -> None:
    before_rows = json.loads((HERE / "before.json").read_text(encoding="utf8"))
    before = {r["id"]: r for r in before_rows}
    assert sorted(before) == sorted([*REPLACEMENTS, 6266]), sorted(before)

    after: dict[int, dict] = {}
    for story_id, pairs in REPLACEMENTS.items():
        after[story_id] = replace_everywhere(before[story_id], pairs)
    after[6266] = {
        "headline": HEADLINE_6266,
        "summary": compose_summary(HEADLINE_6266, FACTS_6266),
        "post_text": POST_6266,
        "facts": FACTS_6266,
    }

    for story_id, row in after.items():
        problems = story_script_bleed(row["headline"], [row["summary"], row["post_text"], *row["facts"]])
        if problems:
            raise SystemExit(f"story {story_id} still carries foreign script: {problems[:3]}")
        if len(row["headline"]) > 500:
            raise SystemExit(f"story {story_id}: headline longer than the 500-character column")

    put(
        HERE / "after.json",
        json.dumps([{"id": i, **after[i]} for i in sorted(after)], ensure_ascii=False, indent=1),
    )

    lines = ["Correction plan, 2026-10-01. Nothing here has been written to production.\n"]
    for story_id in sorted(after):
        old, new = before[story_id], after[story_id]
        lines.append("=" * 100)
        lines.append(f"STORY {story_id}  (video {old['video_id']})")
        if story_id in REPLACEMENTS:
            for o, n, why in REPLACEMENTS[story_id]:
                lines.append(f"  replace  {o!r}  ->  {n!r}\n  because  {why}")
        else:
            lines.append("  full rewrite in English from the transcript segment 17:10-20:35 (see make_plan.py)")
        for field in ("headline", "summary", "post_text"):
            if old[field] != new[field]:
                lines.append(f"  {field.upper()} before: {old[field]}\n  {field.upper()} after : {new[field]}")
        if old["facts"] != new["facts"]:
            for i, (a, b) in enumerate(zip(old["facts"], new["facts"], strict=True)):
                if a != b:
                    lines.append(f"  FACT {i + 1} before: {a}\n  FACT {i + 1} after : {b}")
        url_old = f"/news-archive/{story_slug(old['headline'], story_id)}"
        url_new = f"/news-archive/{story_slug(new['headline'], story_id)}"
        if url_old == url_new:
            lines.append(f"  URL unchanged: {url_new}")
        else:
            lines.append(f"  URL before: {url_old}\n  URL after : {url_new}   (the old one answers 301 to it)")
    put(HERE / "DIFF.txt", "\n".join(lines) + "\n")

    ids = sorted(after)
    put(
        HERE / "APPLY.sql",
        script("Apply: story text corrected (2026-10-01)", [(i, before[i], after[i]) for i in ids]),
    )
    put(
        HERE / "CHECK_BEFORE.sql",
        check_sql("Check: production still holds the 'before' text", [(i, before[i]) for i in ids]),
    )
    put(
        HERE / "CHECK_AFTER.sql",
        check_sql("Check: production holds the 'after' text", [(i, after[i]) for i in ids]),
    )
    put(
        HERE / "ROLLBACK.sql",
        script("Rollback: restore the story text from before.json", [(i, after[i], before[i]) for i in ids]),
    )
    print(f"wrote after.json, DIFF.txt, APPLY.sql, ROLLBACK.sql, CHECK_*.sql for {len(ids)} stories")


if __name__ == "__main__":
    main()

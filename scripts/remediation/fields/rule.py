"""The rule a field run decides under, pinned in the run's own files.

Two rules share every module of this package (`answers`, `handoff`, `plan`, the writer in
`mechanical/lane.py`); a run says which one it is in `RUN.json`, written once when the run is built.

* **two-families** (lane WD1, owner decision O6 of 2026-09-26): a value is replaced only with a
  sourced value, else the field is emptied. "Sourced" is at least two verbatim quotes from two
  independent source families. An exhausted field is cleared (a point is held: it cannot be empty).
* **one-family** (lane WD3, owner decisions of 2026-10-01 - "Wikipedia/Wikidata reicht", "Feld bleibt
  leer", "Recherchieren, sonst behalten"): one verbatim quote from one source suffices, found by
  machine in the page as fetched, and every field check of `answers.py` stays. The run is aimed at
  open fields only and **fills, never clears**: an exhausted field stays as it is (empty, or the
  stored point) and goes to the owner list. Quotes from the site's own pages and from Wikipedia
  mirrors are refused.

A run without `RUN.json` is a WD1 run: the files of those runs were written before the switch
existed, and their prompts are pinned by hash - `read_rule` names the default instead of guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_FILE = "RUN.json"

#: Never a source of WD3 (the rule's brief says so too): the project's own site, the mirrors and
#: re-publishers of Wikipedia the agents are known to reach through a search engine, and the archive,
#: cache and translation proxies - a quote read through one cannot be attributed to a family
#: (`answers.family_of` unwraps a Wayback copy to its original first; what is left is refused). The
#: list is what a machine can refuse; an AI content farm has no list - the brief forbids those, and
#: the owner list shows every written value's quotes.
FORBIDDEN_FAMILIES = frozenset(
    {
        "ancientnerds.com",
        "wikiwand.com",
        "dbpedia.org",
        "wikizero.com",
        "alchetron.com",
        "wikimili.com",
        "en-academic.com",
        "wiki2.org",
        "infogalactic.com",
        "wikibrief.org",
        "archive.org",
        "archive.ph",
        "archive.today",
        "archive.is",
        "archive.md",
        "archive.vn",
        "archive.li",
        "archive.fo",
        "googleusercontent.com",
        "translate.goog",
        "translate.google.com",
    }
)


class RuleError(ValueError):
    """The run's rule is missing, unknown or disagrees with its stage."""


@dataclass(frozen=True)
class Rule:
    """What a run's answers must rest on and what becomes of a field nobody could source.

    `stage` is the handoff stage of the run's answers, the prefix of its batches and the family of
    the write lanes (`fields-<stage>-<wave>-sNNN`). `clearable`: an exhausted field is emptied
    (WD1); otherwise it stays (WD3). `fill_only`: the write plan changes empty and unsourced fields
    only and never rewrites a period label that no written start asks for (WD3).
    """

    name: str
    stage: str
    min_quotes: int
    min_families: int
    forbidden_families: frozenset[str]
    clearable: bool
    fill_only: bool

    @property
    def rests_on(self) -> str:
        """The sentence `answers` refuses a thinner answer with."""
        if self.min_families == 2:
            return (
                "at least two quotes from two independent source families (one Wikipedia "
                "article, its Wikidata item and Commons are one family)"
            )
        return (
            "at least one quote from one source (one Wikipedia article in any language, its "
            "Wikidata item and Commons are one family)"
        )


TWO_FAMILIES = Rule("two-families", "wd1", 2, 2, frozenset(), True, False)
ONE_FAMILY = Rule("one-family", "wd3", 1, 1, FORBIDDEN_FAMILIES, False, True)
RULES = {rule.name: rule for rule in (TWO_FAMILIES, ONE_FAMILY)}
BY_STAGE = {rule.stage: rule for rule in RULES.values()}
#: The rule of a run without `RUN.json`: WD1's, the lane whose runs predate the file.
DEFAULT = TWO_FAMILIES


def read_rule(run: Path) -> Rule:
    """The rule `run` was built under: its `RUN.json`, or `DEFAULT` when the run has none."""
    path = run / RUN_FILE
    if not path.exists():
        return DEFAULT
    data = json.loads(path.read_text(encoding="utf-8"))
    rule = RULES.get(data.get("rule"))
    if rule is None:
        raise RuleError(f"{path}: rule {data.get('rule')!r} is not one of {sorted(RULES)}")
    if data.get("stage") != rule.stage:
        raise RuleError(f"{path}: stage {data.get('stage')!r} is not {rule.name}'s {rule.stage!r}")
    return rule


def write_run(run: Path, rule: Rule, **facts: Any) -> None:
    """RUN.json of a new run - refused when the run already holds one of another rule. The facts
    (when it was built, from what) are recorded beside the rule and are not read back."""
    existing = run / RUN_FILE
    if existing.exists() and read_rule(run) != rule:
        raise RuleError(f"{existing} pins rule {read_rule(run).name!r}, not {rule.name!r}")
    run.mkdir(parents=True, exist_ok=True)
    existing.write_text(
        json.dumps({"rule": rule.name, "stage": rule.stage, **facts}, indent=1, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

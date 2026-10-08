"""The rule a field run decides under, pinned in the run's own files.

Three rules share every module of this package (`answers`, `handoff`, `plan`, the writer in
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
* **one-family-period** (lane WD4, owner decision of 2026-10-04 - "eine benannte Periode ist ein
  Wert"): WD3's rule on a stage of its own, because WD3 is finished and a period word is not its
  answer. Measured on 2026-10-04 in `output/remediation/fields/wd3/DECISIONS.jsonl`: 792 of the
  1,338 `unresolved` `period_start` answers name a period in their own reasoning and 677 of them
  name one a table can turn into years. WD4 asks the same question, adds the answer kind
  `period_name` (`pipeline.periods`), and its batches and write lanes carry `wd4`, so a period run
  can never write into a finished wd3 run.

* **recheck** (lane wd5, owner decisions D10, D12 and D19 of 2026-10-08): WD4's rule aimed at the
  values no source stands behind - a period a named rule made (1,254 sites), a field a MiniMax
  agent decided (calibration failed at 64.71 %), a point nobody sourced - and the one rule whose
  plan *replaces* a stored value, only one of those. A period nobody can source is cleared to the
  label `Undated` when a rule made it; a value a MiniMax agent wrote and Claude cannot source is
  restored from the journal. The answer kinds are WD4's, and `answers.states_year` reads a date in
  years before the present (BP).

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
    only and never rewrites a period label that no written start asks for (WD3). `recheck`: the
    question is asked of a stored value that no source stands behind, and the plan replaces such a
    value (and only such a value); it writes a period label only beside a start it writes or
    clears, like a fill-only rule.
    """

    name: str
    stage: str
    min_quotes: int
    min_families: int
    forbidden_families: frozenset[str]
    clearable: bool
    fill_only: bool
    recheck: bool = False

    @property
    def asks_open_fields(self) -> bool:
        """Whether the question names each field's open reason and the site's own links, and the
        plan keeps a label beside the start it writes: the fill-only rules' and the recheck's."""
        return self.fill_only or self.recheck

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
ONE_FAMILY_PERIOD = Rule("one-family-period", "wd4", 1, 1, FORBIDDEN_FAMILIES, False, True)
RECHECK = Rule("recheck", "wd5", 1, 1, FORBIDDEN_FAMILIES, False, False, True)
RULES = {rule.name: rule for rule in (TWO_FAMILIES, ONE_FAMILY, ONE_FAMILY_PERIOD, RECHECK)}
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

"""The calibration of lane E's writer (`roles.ROLES` `enrich_writer`, sealed as `enrich-writer`): a
leave-one-out truth pool of texts that already carry a sourced open question.

Owner decision D6 (2026-10-08): no role answers a lane before it passed a calibration sealed before
the run (`calibrate_claude.py`). Lane E's pilot approval requires the passed verdict `enrich-writer`
by code (`enrich.require_writer_calibration`, threshold at least 0.7). The descriptions map planned
the pool as "the 20 WN pilot sites through the full chain plus a leave-one-out on about 40 sites
whose text already carries a sourced open question". The WN pilot is lost (its run lived in the
removed worktree `db-finish`) and was MiniMax-judged, so it is no ground truth (master plan X6); this
module builds the leave-one-out part, which stands on its own:

* **the case**: a lane-E basis text (`enrich.classify`) one of whose sentences frames something
  about the site as open - a dating, function or identification scholars cannot settle - and cites a
  page. The orchestrator confirms each case by reading the cited page (`candidates` only proposes);
* **the question**: the production write question (`enrich.enrich_prompt`, the open_question class
  always offered) about the text **without that sentence** - its marker and a citation only it used
  removed, the rest renumbered by first use (`leave_one_out`, through `wc4.compose`, the composer
  every WC write uses);
* **the truth** (`TRUTH.json`, sealed with the pool): the sentence removed and the hosts of the
  pages it cited. A writer that is calibrated finds the open matter again from reputable pages: its
  answer carries an `open_question` sentence (unit `open_question`) resting on a quote from one of
  those hosts (unit `source`). An answer that invents a different mystery shows as a disagreement the
  orchestrator spot-checks (O18: every disagreement's URL and quote, `--false-sources`).

    enrich_calibration.py candidates --run-dir R --out CANDIDATES.jsonl
    enrich_calibration.py build      --run-dir R --cases CASES.jsonl --out DIR [--batch-size 5]
    calibrate_claude.py seal --id enrich-writer --role enrich_writer --handoff DIR/handoff \\
        --batches we-0001 ... --threshold 0.7 --truth DIR/TRUTH.json --comparison enrich-recovery
    calibrate_claude.py prepare --id enrich-writer --run DIR/run
    #   one enrich_writer agent per batch: wc/cli.py brief --run-dir $CAL/enrich-writer-run
    #   --handoff $CAL/enrich-writer --batch-id we-000N ; opus_handoff.py validate --dir $CAL/enrich-writer
    enrich_calibration.py compare --id enrich-writer
    calibrate_claude.py verdict --id enrich-writer --false-sources N

`R` is a run directory holding a fresh read (`wc/cli.py read`). `CASES.jsonl` holds one line per
confirmed case: `{"site_id", "sentence", "confirmed_by", "note"}` (`sentence` is the 1-based number
of the open-question sentence in `checked_sentences` of the stored text). Nothing here calls a model
or writes to production.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_REMEDIATION = Path(__file__).resolve().parents[1]
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

import calibrate_claude as CC  # noqa: E402 - the seal, prepare, compare and verdict
import mcode_driver as D  # noqa: E402 - the comparison's report shape
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import (
    plan4,  # noqa: E402 - a read row as the plan's site
    wc4,  # noqa: E402
)

from wc import cli as WC  # noqa: E402 - the read, the export of a round, the site block
from wc import enrich as E  # noqa: E402

#: The comparison `calibrate_claude.py seal --comparison` names for this pool.
COMPARISON = "enrich-recovery"
TRUTH_FILE = "TRUTH.json"
CASES_KEYS = frozenset({"site_id", "sentence", "confirmed_by", "note"})
#: Units of one case: the answer carries an open_question sentence, and it rests on a quote from a
#: host the removed sentence cited.
PRESENT, ABSENT = "present", "absent"
SAME_HOST, OTHER_HOST, NO_SENTENCE = "same-host", "other-host", "no-open-question"
#: The words that make a sentence a candidate (`candidates`): something about the site is open, in
#: the source's own framing. A proposal for the orchestrator to read, never a decision.
OPEN_WORDS = re.compile(
    r"\b(?:unknown|unclear|uncertain|unresolved|undetermined|debated|disputed|a mystery|"
    r"remains? (?:a matter of|the subject of) (?:debate|speculation|dispute)|"
    r"not (?:yet )?(?:been )?(?:fully )?(?:known|understood|explained|excavated|identified)|"
    r"(?:scholars|archaeologists|researchers|historians) (?:disagree|debate|dispute))\b",
    re.IGNORECASE,
)


class EnrichCalibrationError(ValueError):
    """The pool cannot be built or compared as asked. Nothing is guessed."""


# ------------------------------------------------------------------------------ the text
def sentence_urls(text: str, citations: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Per sentence of `checked_sentences(text)`, the URLs its markers cite, in marker order: each
    marker is placed where it stands in the plain text (`wc4.strip_markers`), and a marker belongs
    to the sentence whose span reaches up to it (markers sit before or after the final mark)."""
    by_number = {int(c["n"]): str(c["url"]) for c in citations}
    plain_markers: list[tuple[int, int]] = []
    removed = 0
    for match in wc4._MARKER.finditer(text):
        plain_markers.append((match.start() - removed, int(match.group().strip()[1:-1])))
        removed += match.end() - match.start()
    plain = wc4.strip_markers(text)
    sentences = wc4.checked_sentences(text)
    ends: list[int] = []
    cursor = 0
    for sentence in sentences:
        start = plain.index(sentence, cursor)
        cursor = start + len(sentence)
        ends.append(cursor)
    urls: list[list[str]] = [[] for _ in sentences]
    for position, number in plain_markers:
        owner = next(i for i, end in enumerate(ends) if position <= end)
        if by_number[number] not in urls[owner]:
            urls[owner].append(by_number[number])
    return urls


def leave_one_out(base: wc4.Base, number: int) -> tuple[wc4.Base, str, list[str]]:
    """`base` without its sentence `number`: the other sentences, each with the markers of the pages
    it cited, renumbered by first use (`wc4.compose`), and the citation list of exactly those pages.
    Returns the new base, the removed sentence and the URLs it cited."""
    sentences = wc4.checked_sentences(base.text)
    if not 1 <= number <= len(sentences):
        raise EnrichCalibrationError(f"sentence {number} of {len(sentences)}")
    if len(sentences) < 2:
        raise EnrichCalibrationError("a one-sentence text has nothing left without its sentence")
    urls = sentence_urls(base.text, base.citations)
    titles = {str(c["url"]): str(c.get("title") or c["url"]) for c in base.citations}
    decisions: list[wc4.Decision] = []
    quotes: dict[int, list[wc4.Quote]] = {}
    for n, sentence in enumerate(sentences, start=1):
        if n == number:
            continue
        if not urls[n - 1]:
            raise EnrichCalibrationError(f"sentence {n} cites no page: not a sourced text")
        kept = len(decisions) + 1
        decisions.append(
            wc4.Decision(
                n=kept, sentence=sentence, verdict=wc4.Verdict.KEEP, remove=None, reason=None
            )
        )
        quotes[kept] = [wc4.Quote(url=u, title=titles[u], quote=sentence) for u in urls[n - 1]]
    composed = wc4.compose(decisions, quotes)
    if composed.description is None:
        raise EnrichCalibrationError("nothing is left")
    return (
        wc4.Base(text=composed.description, citations=composed.citations),
        sentences[number - 1],
        urls[number - 1],
    )


def host(url: str) -> str:
    """The host of a URL, lower case, without a leading `www.`."""
    name = (urlsplit(url).hostname or "").lower()
    return name.removeprefix("www.")


# ------------------------------------------------------------------------------ the candidates
def _sites(run: Path) -> list[tuple[dict[str, Any], M.PlanSite]]:
    out = []
    for row in sorted(read_jsonl(run / WC.ROWS_FILE), key=lambda row: row["id"]):
        site_row = {key: value for key, value in row.items() if key != "scope_status"}
        out.append((row, plan4.plan_site(site_row, flags=frozenset())))
    return out


def candidates(run: Path, out: Path) -> dict[str, Any]:
    """Every sentence of a lane-E basis text (`enrich.classify`, not retired) that frames something
    as open (`OPEN_WORDS`) and cites a page: a proposal the orchestrator confirms by reading the
    page, one line per sentence."""
    lines: list[dict[str, Any]] = []
    for row, site in _sites(run):
        if row["scope_status"] == "retired":
            continue
        reason, marking, sentences = E.classify(site, excluded=set(), earlier=set())
        if reason is not None or len(sentences) < 2:
            continue
        urls = sentence_urls(str(site.description), (site.raw_data or {})[M.CITATIONS_KEY])
        for n, sentence in enumerate(sentences, start=1):
            if OPEN_WORDS.search(sentence) and urls[n - 1]:
                lines.append(
                    {
                        "site_id": site.site_id,
                        "name": site.name,
                        "marking": marking,
                        "sentence": n,
                        "text": sentence,
                        "urls": urls[n - 1],
                    }
                )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
        newline="\n",
    )
    return {"candidates": len(lines), "sites": len({line["site_id"] for line in lines})}


# ------------------------------------------------------------------------------ the pool
def _cases(path: Path) -> list[dict[str, Any]]:
    cases = read_jsonl(path)
    seen: set[str] = set()
    for number, case in enumerate(cases, start=1):
        if set(case) != CASES_KEYS:
            raise EnrichCalibrationError(f"{path}:{number}: a case carries {sorted(CASES_KEYS)}")
        if case["site_id"] in seen:
            raise EnrichCalibrationError(f"{path}:{number}: {case['site_id']} twice")
        if not str(case["confirmed_by"]).strip():
            raise EnrichCalibrationError(f"{path}:{number}: a case is confirmed by someone")
        seen.add(case["site_id"])
    if not cases:
        raise EnrichCalibrationError(f"{path}: no case")
    return cases


def build(run: Path, cases_path: Path, out: Path, *, batch_size: int = 5) -> dict[str, Any]:
    """The pool: `out/run` (a run of kind `wn-enrich` holding one entry per case, the text without
    its open-question sentence, and the round that exported them), `out/handoff` (the write
    questions, no answer) and `out/TRUTH.json` (per case: the open question is present, and the
    hosts its removed sentence cited). Refused: a case that is no lane-E basis, whose sentence
    frames nothing as open or cites no page, and an `out` that is not new."""
    if out.exists():
        raise EnrichCalibrationError(f"{out} exists: a pool is built once")
    cases = _cases(cases_path)
    sites = {site.site_id: (row, site) for row, site in _sites(run)}
    entries: list[dict[str, Any]] = []
    truth: dict[str, dict[str, Any]] = {}
    for case in cases:
        if case["site_id"] not in sites:
            raise EnrichCalibrationError(f"{case['site_id']}: no curated row of the read")
        row, site = sites[case["site_id"]]
        reason, marking, _ = E.classify(site, excluded=set(), earlier=set())
        if row["scope_status"] == "retired" or reason is not None:
            raise EnrichCalibrationError(f"{site.site_id}: not a lane-E basis ({reason})")
        raw = site.raw_data or {}
        stored = wc4.Base(text=str(site.description), citations=tuple(raw[M.CITATIONS_KEY]))
        reduced, removed, urls = leave_one_out(stored, int(case["sentence"]))
        if not OPEN_WORDS.search(removed) or not urls:
            raise EnrichCalibrationError(
                f"{site.site_id}: sentence {case['sentence']} frames nothing as open or cites no "
                f"page: {removed!r}"
            )
        left = dataclasses.replace(
            site,
            description=reduced.text,
            description_sha256=M.text_sha256(reduced.text),
            raw_data={**raw, M.CITATIONS_KEY: [dict(c) for c in reduced.citations]},
        )
        existing = wc4.checked_sentences(reduced.text)
        entry = {
            "site_id": site.site_id,
            "name": site.name,
            "marking": marking,
            "sentences": [],
            "plan_site": left.to_dict(),
        }
        entry.update(E.entry_extras(left, existing))
        entries.append(entry)
        truth[site.site_id] = {
            "open_question": PRESENT,
            "removed": removed,
            "urls": urls,
            "hosts": sorted({host(url) for url in urls}),
            "confirmed_by": case["confirmed_by"],
        }
    pool_run, handoff = out / "run", out / "handoff"
    pool_run.mkdir(parents=True)
    (pool_run / WC.POPULATION_FILE).write_text(
        json.dumps(
            {
                "kind": WC.KIND_ENRICH,
                "pilot": None,
                "calibration": {"id": E.WRITER_CALIBRATION_ID, "cases": len(entries)},
                "read": json.loads((run / WC.READ_FILE).read_text(encoding="utf-8")),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (pool_run / WC.SITES_FILE).write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
        newline="\n",
    )
    summary = WC._export_round(
        pool_run,
        handoff,
        number=1,
        questions=[(entry["site_id"], [], {}) for entry in entries],
        batch_size=batch_size,
    )
    (out / TRUTH_FILE).write_text(
        json.dumps(truth, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    batches = sorted(WC.round_of(pool_run, handoff)["batches"])
    return {
        **summary,
        "cases": len(entries),
        "run": str(pool_run),
        "handoff": str(handoff),
        "truth": str(out / TRUTH_FILE),
        "seal": (
            f"calibrate_claude.py seal --id {E.WRITER_CALIBRATION_ID} --role {E.WRITER_ROLE} "
            f"--handoff {handoff.as_posix()} --batches {' '.join(batches)} --threshold "
            f"{E.WRITER_SEAL_MINIMUM} --truth {(out / TRUTH_FILE).as_posix()} --comparison "
            f"{COMPARISON}"
        ),
    }


# ------------------------------------------------------------------------------ the comparison
def answer_units(text: str) -> tuple[str, str, list[str]] | None:
    """`(open_question, source, urls)` of one writer answer: whether it carries an open_question
    sentence, which hosts its quotes come from, and every URL it quotes (for the spot check). `None`
    for a text that is no enrich answer (unanswered)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        return None
    hooks = [
        s for s in data["sentences"] if isinstance(s, dict) and s.get("class") == wc4.OPEN_QUESTION
    ]
    urls = [
        str(q.get("url"))
        for s in data["sentences"]
        if isinstance(s, dict)
        for q in s.get("quotes") or []
        if isinstance(q, dict)
    ]
    if not hooks:
        return ABSENT, NO_SENTENCE, urls
    hook_hosts = {
        host(str(q.get("url"))) for q in hooks[0].get("quotes") or [] if isinstance(q, dict)
    }
    return PRESENT, ",".join(sorted(hook_hosts)), urls


def compare_recovery(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    """The comparator `enrich-recovery` (`calibrate_claude.compare(comparators=...)`): per case two
    units against the sealed truth - the open question found again (`present`), and resting on a
    quote from a host the removed sentence cited (`same-host`). A case without a fresh answer, or
    with a text that is no enrich answer, is unanswered, never agreement."""
    truth = json.loads(Path(sealed["truth"]).read_text(encoding="utf-8"))
    labels = sorted(truth)
    units = agreed = 0
    disagreements: list[D.Disagreement] = []
    unanswered: list[str] = []
    for label in labels:
        text = fresh.get(label)
        read = None if text is None else answer_units(text)
        if read is None:
            unanswered.append(label)
            continue
        found, hosts, urls = read
        wanted = truth[label]
        same = found == PRESENT and bool(set(hosts.split(",")) & set(wanted["hosts"]))
        pairs = [
            ("open_question", wanted["open_question"], found),
            (
                "source",
                SAME_HOST,
                SAME_HOST if same else (OTHER_HOST if found == PRESENT else NO_SENTENCE),
            ),
        ]
        for unit, expected, got in pairs:
            units += 1
            if expected == got:
                agreed += 1
                continue
            disagreements.append(
                D.Disagreement(
                    label=label,
                    unit=unit,
                    recorded=expected,
                    fresh=got,
                    recorded_sources=tuple(wanted["urls"]),
                    fresh_sources=tuple(urls),
                )
            )
    report = D.Calibration(
        sealed["role"], tuple(labels), units, agreed, tuple(disagreements), tuple(unanswered)
    ).to_dict()
    report["comparison"] = COMPARISON
    return report


COMPARATORS: dict[str, CC.Comparator] = {COMPARISON: compare_recovery}


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="enrich-calibration", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    found = sub.add_parser("candidates")
    found.add_argument("--run-dir", required=True, type=Path)
    found.add_argument("--out", required=True, type=Path)
    pool = sub.add_parser("build")
    pool.add_argument("--run-dir", required=True, type=Path)
    pool.add_argument("--cases", required=True, type=Path)
    pool.add_argument("--out", required=True, type=Path)
    pool.add_argument("--batch-size", type=int, default=5)
    compare = sub.add_parser("compare")
    compare.add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
    compare.add_argument("--id", required=True, dest="calibration_id")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "candidates":
            payload: Any = candidates(args.run_dir, args.out)
        elif args.command == "build":
            payload = build(args.run_dir, args.cases, args.out, batch_size=args.batch_size)
        else:
            payload = CC.compare(
                args.root, calibration_id=args.calibration_id, comparators=COMPARATORS
            )
    except (EnrichCalibrationError, CC.CalibrationError, WC.WcRunError, wc4.WcError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

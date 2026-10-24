"""The calibration of lane WC's roles (owner decision D6, 2026-10-08), on `calibrate_claude.py`.

`calibrate_claude.py verdict` serves lane WC as it stands (a pool is batches of an answered handoff,
the threshold is sealed first). What lane WC adds is here, because it measures what the lane's own
checks measure and nothing else - and it is **sealed with the threshold**, before the copy is made and
any agent answers (`seal`): the kind of pool, the verdict merge and the list of known errors, with its
sha256. `compare` reads them from the seal and takes no setting of its own, and `calibrate_claude.py`
refuses a lane WC calibration it was not asked to seal (`seal`), to compare (`compare`) or to close with
a comparison that did not come from here (`verdict`).

* **the check pool counts KEEP and KEEP_TRIMMED as one verdict** (`merge`): whether a sentence goes
  whole or with a piece cut off is a second decision on a sentence both answers keep, and the
  agreement of the check is on whether it stays (map `descriptions.md`, D25a);
* **known errors** (`expectations`): the pilots' judges found sentences the check kept and was wrong
  to - a kept sentence WRONG with a found quote, a kept text incoherent. A role is calibrated on the
  pilots' sites, so the fresh answer must not keep such a sentence (check pool: neither KEEP nor
  KEEP_TRIMMED; verify pool: it must be WRONG or UNSUPPORTED) and the fresh judge must find it again
  (judge pool: `must_be WRONG`, `coherent must_be False`). A kept text the judge found incoherent is a
  site whose recorded check pattern produced it: the fresh check must not repeat that pattern, and a
  fresh verification or judge must find the text incoherent. A known error the role misses fails the
  calibration whatever the agreement is (`lane_failures`);
* **extra WRONG verdicts** (judge pool): a fresh judge that calls WRONG what the recorded one did not
  is allowed one (`MAX_EXTRA_WRONG`);
* **the texts** (`templates`, X15 of 2026-10-25): the seal binds the sha256 of the kind's question,
  brief and cache note, and `prepare` and `compare` refuse a calibration whose texts changed since (a
  seal made before carries none and binds `TEMPLATES_BEFORE_X15`). A judge pool's copy is asked the
  question the code builds now, and `compare` refuses a copy or a fresh answer to another one;
* **the judge pool is registrable** (`register_judge_pool`): `mcode_driver.register_calibration_run`
  knows the check and the verification rounds, not the judge's, so the calibration run of a judge pool
  is written here (`judge/ROUND.json` marked `calibration`, tied to no plan, the `FINAL.jsonl` lines of its sites).

    python scripts/remediation/wc/calibration.py known   --kind check|verify|judge --run R [--run R ...] [--handoff H]
    python scripts/remediation/wc/calibration.py seal    --id ID --kind K --handoff H --batches B [B ...] --threshold T [--run R ...]
    python scripts/remediation/wc/calibration.py prepare --id ID --run R
    python scripts/remediation/wc/calibration.py compare --id ID

`known` prints what `seal` derives (to review it first; a verify pool names its round with `--handoff`);
`seal` derives the expectations of the pool's sites from the pilots' judged runs and seals them with the
threshold; `prepare` is `calibrate_claude.py prepare` with the judge pool registered; `compare` is
`calibrate_claude.py compare` with the merge and the sealed expectations.
`calibrate_claude.py verdict` closes the calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Collection, Iterable, Sequence
from pathlib import Path
from typing import Any

_REMEDIATION = Path(__file__).resolve().parents[1]
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

import calibrate_claude as CC  # noqa: E402 - seal, prepare, compare, verdict
import mcode_driver as D  # noqa: E402 - the copy, the comparison, the calibration run
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from phase3.ledger import utc_now  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402

from wc import cli as WC  # noqa: E402 - the verification rounds' records
from wc import prompts as P  # noqa: E402 - the frozen texts a seal binds

#: The verdicts of a check answer that count as one (a sentence kept whole or with a piece cut off).
MERGED = frozenset({"KEEP", "KEEP_TRIMMED"})
#: A fresh judge may call WRONG at most this many kept sentences the recorded judge did not.
MAX_EXTRA_WRONG = 1
#: Which role a kind of pool calibrates: the role that answers that kind of round in lane WC
#: (`wc/cli.py`), so a pool is sealed for, and its fresh answers judged against, the role the lane's
#: briefs print and its imports require - the fact checker (Opus since the tier move of wc-fc-1),
#: lane WC's own web verifier `wc_web_verifier` (D45; the shared `web_verifier` failed wc-wv-1/2,
#: `roles.SETTLED_TIER_MOVES`) and the pilot judge.
KIND_ROLE = {"check": WC.ROLE_CHECK, "verify": WC.ROLE_VERIFY, "judge": WC.ROLE_JUDGE}
#: The verdicts a fresh verification may give a sentence the judge found WRONG (it may not support it).
NOT_SUPPORTED = ["UNSUPPORTED", "WRONG"]
JUDGE_ROUND = Path("judge") / "ROUND.json"
#: The frozen texts (`wc/prompts.py`) a kind of pool is asked and briefed with: its question, its
#: brief and the cache note every brief carries. A seal binds their bytes (`templates`), as a teaser
#: seal binds its prompt modules, so a question or brief changed after the seal refuses the
#: calibration's prepare and compare: its agents would answer another prompt than the one sealed
#: (orchestrator decision X15, 2026-10-25).
KIND_TEMPLATES = {
    "check": ("CHECK_QUESTION", "REASK_BLOCK", "CHECK_BRIEF", "WIKI_CACHE_NOTE"),
    "verify": ("VERIFY_QUESTION", "VERIFY_BRIEF", "WIKI_CACHE_NOTE"),
    "judge": ("JUDGE_QUESTION", "JUDGE_BRIEF", "WIKI_CACHE_NOTE"),
}
#: What a seal made before the templates were bound carries none of: the texts in force when every
#: such seal was made (2026-10-24, the pins of `tests/remediation/test_wc.py` since 2026-10-09). Such
#: a seal binds these, so the judge question sharpened by X15 refuses wc-pj-1/2's agents while the
#: check and verify seals of 2026-10-24 (wc-fc-*o, wc-wv-*o) stand on unchanged texts.
TEMPLATES_BEFORE_X15 = {
    "check": {
        "CHECK_QUESTION": "7a7bec8e58f53f5e2f65f6c90ac02ecc345bab6da60cbd6ef78cd4ff9de971c7",
        "REASK_BLOCK": "e1c324db3e2571e70c42bf31f6d5594524014eec67ac0093b9afb0901c92960d",
        "CHECK_BRIEF": "df2eaa3e04a08c70a223f04e54eb8b5164e895c86c134e1badb12b54d69e7b55",
        "WIKI_CACHE_NOTE": "f3bcd218d96ac2a764f33854083ca1f1c2d5df36576c3fac821869b39f1b00ee",
    },
    "verify": {
        "VERIFY_QUESTION": "f2f88204af84597a7ce792bfb364b8d67c696a6c83c0d47814c050a024dc5a82",
        "VERIFY_BRIEF": "112343f6c4151e28e4b46e12747684d43e7f751062777e8f205b77a303a6afbc",
        "WIKI_CACHE_NOTE": "f3bcd218d96ac2a764f33854083ca1f1c2d5df36576c3fac821869b39f1b00ee",
    },
    "judge": {
        "JUDGE_QUESTION": "6aba7d0af909bcfeb5a25766696404ecc0043ff1858bec231d247f00924d495d",
        "JUDGE_BRIEF": "84e03f52b104ee213367dd18958fca4cf6d49927a6b26573cc446b89d504a95d",
        "WIKI_CACHE_NOTE": "f3bcd218d96ac2a764f33854083ca1f1c2d5df36576c3fac821869b39f1b00ee",
    },
}


class WcCalibrationError(ValueError):
    """The calibration cannot take this step. Nothing is guessed."""


# ------------------------------------------------------------------------------------ the merge
def merge(text: str) -> str:
    """A check answer with KEEP_TRIMMED read as KEEP, as JSON; any other answer unchanged."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        return text
    for row in data["sentences"]:
        if isinstance(row, dict) and row.get("verdict") in MERGED:
            row["verdict"] = "KEEP"
    return json.dumps(data, ensure_ascii=False)


# ------------------------------------------------------------------------------ the expectations
def expectations(
    kind: str,
    runs: Iterable[Path],
    *,
    handoff: Path | None = None,
    labels: Collection[str] | None = None,
) -> list[dict[str, Any]]:
    """What the pilots' judges established, as expectations of a fresh answer (label = site id; only
    the sites in `labels` when it is given):

    * `check`: every kept sentence a judge found WRONG with a found quote must not be kept again,
      whole or trimmed (`sentence-<n>`, `must_not_be ["KEEP", "KEEP_TRIMMED"]`; the sentence's number
      is read from the run's FINAL); a site whose kept text the judge found incoherent must not get
      the recorded pattern of verdicts again (`kept-text`, `must_differ_from_recorded`);
    * `verify`: the same sentence must be WRONG or UNSUPPORTED in the verification of `handoff` (a
      round of each run; `kept-<k>`, k the sentence's place in what that round showed), and a site
      whose kept text the judge found incoherent must be found incoherent (`coherent`, `False`);
    * `judge`: the same sentence must be found WRONG again (`kept-<k>`, `must_be ["WRONG"]`), and a
      site whose kept text the judge found incoherent must be found incoherent (`coherent`,
      `must_be ["False"]`)."""
    if kind not in KIND_ROLE:
        raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")
    if kind == "verify" and handoff is None:
        raise WcCalibrationError("a verify pool names the verification round it is: --handoff")
    found: list[dict[str, Any]] = []
    for run in runs:
        finals = {row["site_id"]: row for row in read_jsonl(run / "FINAL.jsonl")}
        shown = WC._verify_round_of(run, handoff)["shown"] if kind == "verify" and handoff else {}
        for judged in read_jsonl(run / "judge" / "JUDGED.jsonl"):
            site_id = judged["site_id"]
            if labels is not None and site_id not in labels:
                continue
            kept_numbers = [d["n"] for d in finals[site_id]["decisions"] if d["text"] is not None]
            for item in judged["items"]:
                if item["kind"] == "kept" and item["verdict"] == "WRONG" and item["quotes_found"]:
                    k = item["number"]
                    if kind == "check":
                        found.append(
                            {
                                "label": site_id,
                                "unit": f"sentence-{kept_numbers[k - 1]}",
                                "must_not_be": sorted(MERGED),
                            }
                        )
                    elif kind == "verify":
                        number = kept_numbers[k - 1]
                        if number not in shown[site_id]:
                            raise WcCalibrationError(
                                f"{site_id}: the judge's WRONG sentence {number} is not among the "
                                f"sentences {handoff} showed ({shown[site_id]})"
                            )
                        found.append(
                            {
                                "label": site_id,
                                "unit": f"kept-{shown[site_id].index(number) + 1}",
                                "must_be": NOT_SUPPORTED,
                            }
                        )
                    else:
                        found.append({"label": site_id, "unit": f"kept-{k}", "must_be": ["WRONG"]})
            if not judged["coherent"]:
                found.append(
                    {"label": site_id, "unit": "kept-text", "must_differ_from_recorded": True}
                    if kind == "check"
                    else {"label": site_id, "unit": "coherent", "must_be": ["False"]}
                )
    return found


def _units(text: str) -> dict[str, str]:
    pairs = D._verdicts(text)
    return dict(pairs) if pairs is not None else {}


def _sentences(text: str) -> dict[str, str]:
    return {unit: verdict for unit, verdict in _units(text).items() if unit.startswith("sentence-")}


def _known(
    known: Sequence[dict[str, Any]], fresh: dict[str, str], recorded: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every expectation against the fresh answer (unmerged, as the role wrote it): its verdict and
    whether the role missed it. An expectation about a label the pool does not hold stops the
    command: it would measure nothing."""
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for expectation in known:
        label, unit = expectation["label"], expectation["unit"]
        if label not in recorded:
            raise WcCalibrationError(f"expectation {label}/{unit}: the label is not in the pool")
        if expectation.get("must_differ_from_recorded"):
            repeated = label in fresh and _sentences(fresh[label]) == _sentences(recorded[label])
            if label not in fresh:
                verdict = None
            else:
                verdict = "the recorded verdicts" if repeated else "other verdicts"
            missed = verdict is None or repeated
            wanted: Any = "other verdicts than the recorded ones"
        else:
            verdict = _units(fresh[label]).get(unit) if label in fresh else None
            missed = (
                verdict is None
                or ("must_not_be" in expectation and verdict in expectation["must_not_be"])
                or ("must_be" in expectation and verdict not in expectation["must_be"])
            )
            wanted = expectation.get("must_be") or f"not {expectation.get('must_not_be')}"
        rows.append({**expectation, "fresh": verdict, "missed": missed})
        if missed:
            failures.append(
                f"known error {label}/{unit} missed: the fresh answer says {verdict!r}"
                f", expected {wanted}"
            )
    return rows, failures


def _extra_wrong(recorded: dict[str, str], fresh: dict[str, str]) -> int:
    count = 0
    for label, text in fresh.items():
        old = _units(recorded[label]) if label in recorded else {}
        count += sum(
            1
            for unit, verdict in _units(text).items()
            if unit.startswith("kept-") and verdict == "WRONG" and old.get(unit) != "WRONG"
        )
    return count


# ------------------------------------------------------------------------------ the pool's role
def round_role(kind: str, run: Path) -> str:
    """The role that answers `run`'s rounds of this kind of pool in lane WC: `cli.check_role` for a
    check pool (the fact checker; an adversarial or enrichment run answers in another role),
    `cli.verify_role` for a verify pool (`wc_web_verifier`; an enrichment run's verifier is lane E's
    `web_verifier`), the pilot judge for a judge pool."""
    if kind == "check":
        return WC.check_role(run)
    if kind == "verify":
        return WC.verify_role(run)
    if kind == "judge":
        return WC.ROLE_JUDGE
    raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")


def _need_round_role(kind: str, run: Path, calibration_role: str) -> None:
    """Refuse a pool whose source run answers this kind of round in another role than the one the
    calibration measures: the measurement would stand for a role that never answers those rounds."""
    answered_in = round_role(kind, run)
    if answered_in != calibration_role:
        raise WcCalibrationError(
            f"{run}: its {kind} rounds are answered as {answered_in}, but a lane WC {kind} pool "
            f"calibrates {calibration_role}"
        )


# ------------------------------------------------------------------------------------- the seal
def _sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def templates(kind: str) -> dict[str, str]:
    """The sha256 of each frozen text a pool of this kind is asked and briefed with, as they are now."""
    if kind not in KIND_TEMPLATES:
        raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")
    return {
        name: hashlib.sha256(getattr(P, name).encode("utf-8")).hexdigest()
        for name in KIND_TEMPLATES[kind]
    }


def _need_unchanged_templates(calibration_id: str, lane: dict[str, Any]) -> None:
    """Refuse a calibration whose question or brief changed after its seal: its agents answer, or
    answered, another prompt than the one the seal binds. A seal made before the templates were bound
    binds `TEMPLATES_BEFORE_X15`."""
    sealed = lane.get("templates", TEMPLATES_BEFORE_X15[lane["kind"]])
    now = templates(lane["kind"])
    moved = sorted(name for name in set(sealed) | set(now) if sealed.get(name) != now.get(name))
    if moved:
        raise WcCalibrationError(
            f"{', '.join(moved)} changed after {calibration_id} was sealed: its agents answer "
            "another prompt than the sealed one - seal a new calibration"
        )


def _need_current_judge_prompts(out: Path, batches: Sequence[str]) -> None:
    """Refuse a judge pool whose copy does not ask the question the code builds now, and a fresh
    answer to another prompt (`opus_handoff.read_answer` names it stale). A missing answer is left to
    the comparison, which counts it unanswered."""
    run_dir = D.calibration_run(out)
    finals, sites, kind = WC._finals(run_dir), WC.read_sites(run_dir), WC.run_kind(run_dir)
    for batch in batches:
        for (stage, label), line in OH.read_manifest(out, batch).items():
            prompt = _judge_prompt(finals, sites, kind, label)
            if (out / line["prompt_path"]).read_text(encoding="utf-8") != prompt:
                raise WcCalibrationError(
                    f"{out.name}: the question {batch}/{label} is not the one the code builds now: "
                    "the copy was prepared under another judge question - seal a new calibration"
                )
            if (out / line["answer_path"]).exists():
                OH.read_answer(out, batch_id=batch, stage=stage, label=label, prompt=prompt)


def _judge_prompt(
    finals: dict[str, dict[str, Any]], sites: dict[str, dict[str, Any]], kind: str, label: str
) -> str:
    site = WC.M.PlanSite.from_dict(sites[label]["plan_site"])
    return WC.judge_prompt(finals[label], site, kind)


def seal(
    root: Path,
    *,
    calibration_id: str,
    kind: str,
    handoff: Path,
    batches: Sequence[str],
    threshold: float,
    runs: Sequence[Path] = (),
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """`calibrate_claude.seal` for a lane WC pool, with the lane's conditions sealed in it: the kind
    (which fixes the role and whether KEEP and KEEP_TRIMMED are one verdict) and the known errors of
    the pool's sites, derived from the pilots' judged `runs`, with their sha256. A known error of a
    site outside the pool is named (`outside_pool`), never dropped silently."""
    if kind not in KIND_ROLE:
        raise WcCalibrationError(f"kind {kind!r} is none of {', '.join(KIND_ROLE)}")
    for run in runs:
        _need_round_role(kind, run, KIND_ROLE[kind])
    pool = {case.partition("/")[2] for case in CC.case_ids(handoff, batches)}
    found = expectations(kind, runs, handoff=handoff if kind == "verify" else None)
    inside = [e for e in found if e["label"] in pool]
    lane = {
        "kind": kind,
        "merge": kind == "check",
        "expectations": inside,
        "expectations_sha256": _sha256(inside),
        "outside_pool": sorted({e["label"] for e in found if e["label"] not in pool}),
        "templates": templates(kind),
    }
    return CC.seal(
        root,
        calibration_id=calibration_id,
        role=KIND_ROLE[kind],
        handoff=handoff,
        batches=batches,
        threshold=threshold,
        lane=lane,
        now=now,
    )


def _lane(root: Path, calibration_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The seal of a lane WC calibration and its lane conditions, as they were sealed."""
    sealed = CC._sealed(root, calibration_id)
    lane = sealed.get("lane")
    if lane is None:
        raise WcCalibrationError(
            f"{calibration_id} was sealed without the lane's conditions: seal it with "
            "`wc/calibration.py seal` (a threshold and the known errors are sealed together)"
        )
    if lane["expectations_sha256"] != _sha256(lane["expectations"]):
        raise WcCalibrationError(f"the sealed expectations of {calibration_id} were changed")
    return sealed, lane


def prepare(root: Path, *, calibration_id: str, run: Path) -> dict[str, Any]:
    """`calibrate_claude.prepare` of a sealed lane WC pool, the judge pool registered. Refused when
    `run` answers the pool's kind of round in another role than the sealed one (`round_role`)."""
    sealed, lane = _lane(root, calibration_id)
    _need_unchanged_templates(calibration_id, lane)
    _need_round_role(lane["kind"], run, sealed["role"])
    return CC.prepare(root, calibration_id=calibration_id, run=run, register=register_judge_pool)


def compare(root: Path, *, calibration_id: str) -> dict[str, Any]:
    """`calibrate_claude.compare` for lane WC: the fresh answers against the recorded ones, unit by
    unit (KEEP and KEEP_TRIMMED as one when the seal says so), then the sealed known errors and, for a
    judge pool, the extra WRONG verdicts; written once to `COMPARISON.json`, with `lane_failures`
    that `calibrate_claude.py verdict` requires and counts. The merge and the known errors are the
    seal's: there is no setting to pass."""
    sealed, lane = _lane(root, calibration_id)
    _need_unchanged_templates(calibration_id, lane)
    out = root / calibration_id
    recorded_path = out / CC.RECORDED_FILE
    if not recorded_path.exists():
        raise WcCalibrationError(f"{calibration_id} is not prepared: {recorded_path} is missing")
    if lane["kind"] == "judge":
        _need_current_judge_prompts(out, sealed["batches"])
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    fresh = CC._fresh_answers(out, sealed)
    read = merge if lane["merge"] else (lambda text: text)
    report = D.compare_answers(
        sealed["role"],
        sorted(recorded),
        {label: read(text) for label, text in recorded.items()},
        {label: read(text) for label, text in fresh.items()},
    ).to_dict()
    rows, failures = _known(lane["expectations"], fresh, recorded)
    extra = _extra_wrong(recorded, fresh) if lane["kind"] == "judge" else 0
    if extra > MAX_EXTRA_WRONG:
        failures.append(f"{extra} extra WRONG verdict(s), {MAX_EXTRA_WRONG} allowed")
    report.update(
        {
            "kind": lane["kind"],
            "merged": lane["merge"],
            "known": rows,
            "extra_wrong": extra,
            "lane_failures": failures,
        }
    )
    CC._write_once(out / CC.COMPARISON_FILE, report)
    return report


# ------------------------------------------------------------------------------ the judge's pool
def register_judge_pool(
    source_run: Path, source_handoff: Path, out: Path, batches: Sequence[str]
) -> Path:
    """The calibration run of a judge pool: `judge/ROUND.json` (the source's, restricted to the
    calibrated batches and marked `calibration`) and the `FINAL.jsonl` lines of its sites, which are
    what `judge-brief` and `judge-check-answer` read. Any other pool goes to
    `mcode_driver.register_calibration_run`."""
    round_path = source_run / JUDGE_ROUND
    if not round_path.exists():
        return D.register_calibration_run(source_run, source_handoff, out, batches)
    record = json.loads(round_path.read_text(encoding="utf-8"))
    if Path(record["handoff"]).resolve() != source_handoff.resolve():
        return D.register_calibration_run(source_run, source_handoff, out, batches)
    missing = [batch for batch in batches if batch not in record["batches"]]
    if missing:
        raise WcCalibrationError(
            f"{source_handoff}: no batch {', '.join(missing)} in the judge round"
        )
    run_dir = D.calibration_run(out)
    if run_dir.exists():
        raise WcCalibrationError(f"{run_dir} exists: a calibration run is written once")
    labels = [label for batch in batches for label in record["batches"][batch]]
    (run_dir / "judge").mkdir(parents=True)
    (run_dir / "POPULATION.json").write_text(
        json.dumps({"kind": WC.run_kind(source_run), "pilot": None}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    calibration_round = {
        "handoff": D._shown(out),
        "exported_at": record.get("exported_at", ""),
        "batches": {batch: list(record["batches"][batch]) for batch in batches},
        "calibration": True,
        "calibrated_from": {
            "run": D._shown(source_run),
            "handoff": D._shown(source_handoff),
            "batches": list(batches),
        },
    }
    (run_dir / JUDGE_ROUND).write_text(
        json.dumps(calibration_round, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (run_dir / "FINAL.jsonl").write_text(
        D._labels_of(source_run / "FINAL.jsonl", labels), encoding="utf-8"
    )
    (run_dir / WC.SITES_FILE).write_text(
        D._labels_of(source_run / WC.SITES_FILE, labels), encoding="utf-8"
    )
    _ask_with_current_question(run_dir, out, calibration_round["batches"])
    return run_dir


def _ask_with_current_question(run_dir: Path, out: Path, batches: dict[str, list[str]]) -> None:
    """Export the calibrated judge questions of the copy again, built by the code as it stands (the
    site's final text with the question the seal binds): the copy holds them as the pilot's round
    asked them, and a calibration measures the judge on the question it will be asked. The recorded
    answers stay the gold. Their answers are not in the copy (`copy_for_calibration`), so no answer
    is left to a question that changed."""
    finals, sites, kind = WC._finals(run_dir), WC.read_sites(run_dir), WC.run_kind(run_dir)
    for batch, labels in batches.items():
        lines = OH.read_manifest(out, batch)
        if set(lines) != {(WC.JUDGE_STAGE, label) for label in labels}:
            raise WcCalibrationError(
                f"{out / batch}: the manifest is not the judge round's questions of the batch"
            )
        for line in lines.values():
            (out / line["prompt_path"]).unlink()
        (out / batch / OH.MANIFEST_FILE).unlink()
        for label in labels:
            OH.export(
                out,
                batch_id=batch,
                stage=WC.JUDGE_STAGE,
                label=label,
                field=lines[(WC.JUDGE_STAGE, label)]["field"],
                prompt=_judge_prompt(finals, sites, kind, label),
            )


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="wc-calibration", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    known = sub.add_parser("known")
    known.add_argument("--kind", required=True, choices=sorted(KIND_ROLE))
    known.add_argument("--run", required=True, type=Path, action="append")
    known.add_argument("--handoff", type=Path, default=None)
    for name in ("seal", "prepare", "compare"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
        command.add_argument("--id", required=True, dest="calibration_id")
    sealing = sub.choices["seal"]
    sealing.add_argument("--kind", required=True, choices=sorted(KIND_ROLE))
    sealing.add_argument("--handoff", required=True, type=Path)
    sealing.add_argument("--batches", required=True, nargs="+")
    sealing.add_argument("--threshold", required=True, type=float)
    sealing.add_argument("--run", type=Path, action="append", default=[])
    sub.choices["prepare"].add_argument("--run", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "known":
            payload: Any = expectations(args.kind, args.run, handoff=args.handoff)
        elif args.command == "seal":
            payload = seal(
                args.root,
                calibration_id=args.calibration_id,
                kind=args.kind,
                handoff=args.handoff,
                batches=args.batches,
                threshold=args.threshold,
                runs=args.run,
            )
        elif args.command == "prepare":
            payload = prepare(args.root, calibration_id=args.calibration_id, run=args.run)
        else:
            payload = compare(args.root, calibration_id=args.calibration_id)
    except (
        WcCalibrationError,
        WC.WcRunError,
        CC.CalibrationError,
        RO.RoleError,
        OH.HandoffError,
        D.DriverError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

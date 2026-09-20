#!/usr/bin/env python3
"""Phase 3: Merge rewrite outputs into card_descriptions.json, then re-validate.

Reads:  output/rewrite_output_00..09.json
Reads:  output/card_descriptions.json (original)
Writes: output/card_descriptions.json (candidate)
Copies: public/data/card_descriptions.json - ONLY on a complete, valid, non-regressing run

WHY THIS SCRIPT IS WRITTEN THIS WAY (it used to be a script that could not fail)
The previous version reported success in situations where it had done nothing or done harm. Measured,
same fixture, all ten batch files missing:

  OLD (HEAD): exit 0 - and it overwrote public/data/card_descriptions.json with its own input
  NEW       : exit 2 - "FATAL: 10 of 10 batch file(s) missing: [0..9]. Nothing was written."

  * every batch file missing -> the old version printed `WARNING: Missing batch files: [0..9]`, then
    wrote card_descriptions.json and copied it to public/data/ anyway;
  * a batch carrying invalid rewrites -> the errors were printed, and then the *valid subset* was
    applied, because the apply loop never consulted `errors`;
  * the re-validation at the end -> `subprocess.run` was called and **its return code was never
    read**, and `verify_descriptions.py` contains no `sys.exit` at all, so that return code is
    always 0. Gating on it would have been a guard that cannot fail.

`sys.exit` appeared zero times in it. A caller could not distinguish "merged 4,996 rewrites" from
"found no input and overwrote the deploy file with a copy of itself".

This version fails closed. It writes NOTHING to public/data/ unless every one of these holds: all ten
batches present, every rewrite valid, at least one rewrite, the description count unchanged, and the
re-validation flagging no more descriptions than before. Any failure exits non-zero, leaves
public/data/ untouched, and restores output/card_descriptions.json to its pre-run content so the
working tree is not left half-changed.

Two notes on how failures are reported, because the distinction matters here:

  * An input that is missing or unreadable is converted into a specific, loud failure (MergeInputError
    -> EXIT_INPUT naming the file). That is not error-swallowing: nothing is published and the run
    still fails. It replaces a bare traceback with the name of the file that broke. Unexpected
    exceptions are deliberately NOT caught - a bug in this script must not be able to look like bad
    input, which is why there is no blanket `except Exception` here.
  * Both writes go through a temp file and `os.replace`. Writing in place with mode "w" truncates
    first, so a failure part-way through the dump would leave a *truncated* card_descriptions.json -
    including the file api/main.py imports at startup. An atomic replace cannot leave a half file.

Note on the validation gate: it compares the flagged COUNT before and after, because
verify_descriptions.py's exit code carries no information. That script checks no facts (it counts
repeated openers, overused 4-grams, country mentions, hedging, filler, discovery phrasing); the plan
retires it as a gate for exactly that reason. It is used here only to detect a regression introduced
by a merge, which is what the original docstring claimed it did.

Exit codes: 1 input missing/unreadable, 2 incomplete batches, 3 invalid rewrites,
4 nothing to merge, 5 re-validation regressed, 6 description count changed.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
PUBLIC = ROOT / "public" / "data" / "card_descriptions.json"
DESCRIPTIONS = OUTPUT / "card_descriptions.json"
FLAGS = OUTPUT / "verification_flags.json"

NUM_BATCHES = 10
MAX_LEN = 200  # card_stats.card_description is varchar(200); see docs/procedures/FIELD_CONTRACT.md
SENTENCE_ENDINGS = '.!?\'"'
VERIFY = ROOT / "scripts" / "verify_descriptions.py"

EXIT_INPUT = 1
EXIT_INCOMPLETE = 2
EXIT_INVALID = 3
EXIT_NOTHING = 4
EXIT_REGRESSED = 5
EXIT_COUNT_CHANGED = 6


class MergeInputError(Exception):
    """A file this script depends on is missing, unreadable or malformed.

    Reported as EXIT_INPUT with the file named. Never ignored, never turned into a default value.
    """


def read_json(path, what):
    """Read JSON, turning an unreadable or malformed file into a loud, specific failure."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise MergeInputError(f"{what} is missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise MergeInputError(f"{what} is not valid JSON: {path}: {exc}") from None
    except OSError as exc:
        raise MergeInputError(f"{what} could not be read: {path}: {exc}") from None


def write_json_atomic(path, document):
    """Write via a temp file plus os.replace, so an interrupted write cannot truncate the target."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        # The target is untouched at this point - remove the half-written temp file rather than
        # leave litter beside the deploy data.
        tmp.unlink(missing_ok=True)
        raise MergeInputError(f"{path} could not be written: {exc}") from None


def copy_atomic(src, dst):
    """Copy so that a failure cannot leave a truncated destination."""
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError as exc:
        raise MergeInputError(f"{dst} could not be written: {exc}") from None


def collect_rewrites():
    """Return (rewrites, missing_batch_indexes). Raises MergeInputError on an unreadable batch."""
    rewrites = {}
    missing = []
    for i in range(NUM_BATCHES):
        path = OUTPUT / f"rewrite_output_{i:02d}.json"
        if not path.exists():
            missing.append(i)
            continue
        batch = read_json(path, f"batch {i:02d}").get("rewrites", {})
        print(f"  batch {i:02d}: {len(batch)} rewrites")
        rewrites.update(batch)
    return rewrites, missing


def validate(rewrites, descs):
    """Return a list of error strings. An empty list means every rewrite is applicable."""
    errors = []
    for sid, new_desc in rewrites.items():
        if sid not in descs:
            errors.append(f"unknown site_id: {sid}")
            continue
        if not isinstance(new_desc, str):
            errors.append(f"not a string ({type(new_desc).__name__}): {sid}")
            continue
        if not new_desc:
            errors.append(f"empty: {sid}")
            continue
        if len(new_desc) > MAX_LEN:
            errors.append(f"too long ({len(new_desc)} > {MAX_LEN}): {sid}")
        if new_desc[-1] not in SENTENCE_ENDINGS:
            errors.append(f"bad ending ({new_desc[-1]!r}): {sid}")
    return errors


def run_verification():
    """Run verify_descriptions.py and return (flagged_count, returncode).

    The return code signals only whether the script RAN - it contains no sys.exit, so a run that
    finds nothing wrong and a run that finds everything wrong both exit 0. Findings are read from
    the JSON the script writes.
    """
    result = subprocess.run(
        [sys.executable, str(VERIFY)], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return None, result.returncode
    if not FLAGS.exists():
        return None, result.returncode
    return read_json(FLAGS, "the verification output")["flagged_count"], result.returncode


def fail(code, message):
    print(f"\nFATAL: {message}")
    return code


def merge():
    if not DESCRIPTIONS.exists():
        return fail(
            EXIT_INPUT,
            f"{DESCRIPTIONS} does not exist. See the bootstrap in "
            "docs/procedures/FIELD_CONTRACT.md (copy public/data/card_descriptions.json back).",
        )

    original = read_json(DESCRIPTIONS, "the description file")
    descs = original["descriptions"]
    original_count = len(descs)
    print(f"original: {original_count} descriptions")

    # 1. All ten batches, or nothing happens.
    print(f"reading {NUM_BATCHES} batches from {OUTPUT}")
    rewrites, missing = collect_rewrites()
    if missing:
        return fail(
            EXIT_INCOMPLETE,
            f"{len(missing)} of {NUM_BATCHES} batch file(s) missing: {missing}. "
            "Nothing was written. A partial merge is not a merge.",
        )

    # 2. Something to merge, or nothing happens.
    if not rewrites:
        return fail(EXIT_NOTHING, f"the {NUM_BATCHES} batches are present but contain 0 rewrites.")

    # 3. Every rewrite valid, or nothing happens. No partial apply - a batch that carries one
    #    invalid rewrite is not trustworthy for the rest of its contents.
    errors = validate(rewrites, descs)
    if errors:
        print(f"\nvalidation errors ({len(errors)}):")
        for e in errors[:30]:
            print(f"  {e}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more")
        return fail(
            EXIT_INVALID,
            f"{len(errors)} invalid rewrite(s). Nothing was written; the valid subset was NOT "
            "applied on its own.",
        )
    print(f"validated {len(rewrites)} rewrites")

    # 4. Baseline before the merge.
    before, rc = run_verification()
    if before is None:
        return fail(
            EXIT_INPUT,
            f"the baseline verification could not be read (returncode {rc}, {FLAGS} missing?). "
            "Without a baseline the regression check cannot run, and a check that cannot run must "
            "not pass silently.",
        )
    print(f"baseline: {before} descriptions flagged")

    # 5. Write the candidate, re-validate, and roll the working copy back if it regressed. The
    #    rollback restores the document as it was read, so a failed run leaves the working tree in
    #    its pre-run state - not half-changed.
    candidate = dict(descs)
    for sid, new_desc in rewrites.items():
        candidate[sid] = new_desc

    if len(candidate) != original_count:
        return fail(
            EXIT_COUNT_CHANGED,
            f"the merge changed the description count {original_count} -> {len(candidate)}. "
            "This script replaces values; it must never add or drop a site.",
        )

    merged = dict(original)
    merged["descriptions"] = candidate
    write_json_atomic(DESCRIPTIONS, merged)
    print(f"wrote candidate with {len(candidate)} descriptions")

    after, rc = run_verification()
    if after is None:
        write_json_atomic(DESCRIPTIONS, original)
        return fail(
            EXIT_INPUT,
            f"the re-validation could not be read (returncode {rc}). The working copy was rolled "
            "back to its pre-run content and public/data/ was not touched.",
        )
    print(f"after merge: {after} descriptions flagged (baseline {before})")

    if after > before:
        write_json_atomic(DESCRIPTIONS, original)
        return fail(
            EXIT_REGRESSED,
            f"the merge flagged {after - before} more description(s) than before "
            f"({before} -> {after}). The working copy was rolled back to its pre-run content and "
            "public/data/ was NOT touched.",
        )

    # 6. Only now is the deploy-relevant file written.
    copy_atomic(DESCRIPTIONS, PUBLIC)
    print(f"copied to {PUBLIC}")
    print(f"OK: applied {len(rewrites)} rewrites, flag count {before} -> {after}")
    return 0


def main():
    # mypy: sys.stdout is typed TextIO, which does not declare `reconfigure` even though the real
    # stream (io.TextIOWrapper) has it. Nine other scripts in this repo use the identical line; this
    # call is required, not cosmetic - verify_descriptions.py's stdout is forwarded below and can
    # carry non-ASCII description text, which raises UnicodeEncodeError on a cp1252 console.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    try:
        return merge()
    except MergeInputError as exc:
        return fail(EXIT_INPUT, str(exc))


if __name__ == "__main__":
    sys.exit(main())

"""Stage "model" of the Phase-3 runner: one non-interactive Pi process per judgement.

The transport is decided and measured, not chosen here. A Pi process in `--mode json` is the
model driver, invoked from an argv list:

    pi -p --mode json -ne -nt -nc --no-session --model opencode-go/deepseek-v4.1-flash
       --thinking off < prompt

* `-p`          one non-interactive run, no TUI.
* prompt on **stdin**, never in argv. Measured 2026-09-21: a real prompt (one site record plus its
                evidence, ~24,000 characters) passed as the last argv element made `pi.cmd` fail
                with `Die Befehlszeile ist zu lang.` - `pi.cmd` is a batch file, so Windows runs
                it through `cmd.exe`, whose command line stops near 8,191 characters. The same
                shape of prompt on stdin answered normally: 445 input tokens, $0.00006735, and a
                one-word answer. Stdin has no such bound, and a prompt that is never an argv
                element never needs quoting either.
* `--mode json` one JSON object per line on stdout; the settled usage of the assistant message
                arrives in the `message_end` event at `message.usage`.
* `-nt`         **no tools.** The runner fetches the evidence (`phase3/fetch_stage.py`) and the
                model only judges it, so the model can neither fetch a page nor edit a record.
* `-nc`         do not load `CLAUDE.md`/`AGENTS.md`. That removes a measured ~31,500-token fixed
                overhead per lifecycle (the figure the project's working rules state).
* `-ne`         do not load extensions. Measured, not estimated: two live calls with an identical
                prompt on 2026-09-21 by the supervisor --

                    extensions loaded: 14,013 ms wall, input 2,271 tokens, cost $0.00034125
                    with `-ne`       :  2,698 ms wall, input   437 tokens, cost $0.00006615

                i.e. extensions inject ~1,830 tokens into *every* call, and cost 5.2x the money
                and 5x the wall time. Nothing in this design needs an extension: the model judges
                text the runner already fetched. Dropping `-ne` to "simplify" re-buys all of it.
* `--thinking off` the reasoning budget adds tokens to a judgement this narrow and prices it.

Three things this module refuses to do, because each of them is an invisible cost or an invented
number:

1. **It never computes a cost.** The provider reports `cost.total` per call and that reported
   number is what `phase3.ledger` stores (`cost_usd`). Piece 1 recorded tokens only, on the
   ground that a price table is an assumption; the provider's own figure is a measurement, so it
   is recorded and no price is ever applied to a token count here.
2. **It never writes an unmeasured call.** A non-zero exit, a timeout, a stream that does not
   parse, a missing `message_end` usage block or an empty assistant text all raise. Usage is
   never defaulted to zero and an empty answer is never returned as a result. A call that fails
   *after* the provider billed it is therefore not in the ledger - the ledger refuses a line it
   cannot total - which is stated here rather than papered over.
3. **It never retries.** A retry doubles the charge invisibly. Nothing in this module calls the
   runner twice for one `ModelCall`; a re-run of the stage is a second `judge` invocation, and it
   writes its own ledger lines.

`--dry-run` (the default of `phase3 run judge`) renders the exact argv and the exact prompt text
through `pi_argv` / `Prompt.render` without starting a process, so a batch is readable - and its
prompt sizes are visible - before any money is spent.

Piece 4 added the two halves of "partial evidence" whose absence the first live batch exposed. The
batch died because one Overpass request timed out and no evidence file was written for it, and
`prepare_call` then refused to build the prompt - correctly, and on its own terms:

* **A failure the fetch stage recorded is not a hole in the record.** `read_fetch_failures` reads
  the batch's own `fetch.json`, so a target whose file is missing *because that target failed* is
  named in the prompt as failed (`<failed_target ... />` in a `<failed_targets>` block plus
  `PARTIAL_EVIDENCE_NOTE`), and the model can answer `unverifiable` about what it could not see.
  Evidence that is missing with **nothing recorded about it** still raises (`EvidenceUnusable`).
* **A site with no evidence at all buys no model call.** It is recorded as an `unverifiable`
  `Finding` per census finding, carrying the reason, in the batch report. Spending a call to ask a
  model about a page that was never read would buy a guess; writing nothing would hide it.

Three of this module's pieces are reused *outside* it, by the discover pass
(`phase3/discover_stage.py`, piece 5), and each one is a seam rather than a shorthand:

* `evidence_excerpts` and `check_evidence_bound` are the evidence selection and the size guard, so
the discover pass's one-prompt-per-(site, field) calls are built through the same code and cannot
drift from the per-site prompt;
* `ModelCall.field` (with `answer_key`) is what makes five calls for one site five records instead
of one - `judge_site` stores an answer under the call's key, and the fetch stage's own store refuses
to write different bytes over an existing file;
* `EvidenceOverBound` is the one `EvidenceUnusable` case that must **not** end a batch: "the evidence
was too large to judge" is a fact about the evidence, and the discover pass records it as that
site's own `unverifiable` outcome while the batch carries on. Evidence that is missing with
**nothing** recorded about it still stops the batch - that is a hole in the record, not weather.

What this module does not do, stated so it is not mistaken for covered: it does not parse the
model's answer into `phase3.model.Finding` records (that is the next piece - here the answer is
stored verbatim as bytes, one file per `(site, stage)`) - with the one exception of that recorded
`unverifiable` case, which has no answer to parse - and it does not judge `stopReason`: a
`length`-truncated answer would be recorded like any other. Both are named in
`output/remediation/phase3_runner/PIECE3.md`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Dual use: `python -m phase3.model_stage` and `python scripts/remediation/phase3/model_stage.py`.
# The package is not installed, so the parent directory must be importable first (same shim as
# `run.py` and `fetch_stage.py`).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402  - the evidence this stage reads
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402  - the census vocabulary a verdict is spelled in
from phase3 import search_evidence as SE  # noqa: E402  - the search lane's stored hits
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: Provider and model as the probe transcripts record them (`provider: opencode-go`,
#: `model: deepseek-v4.1-flash`) and as the brief names the id. Given, not chosen.
PROVIDER = "opencode-go"
MODEL = "opencode-go/deepseek-v4.1-flash"
THINKING = "off"

#: The launcher and the flags, in the order the transport was measured with. See the module
#: docstring for what each flag buys; `-ne`'s numbers are measured, not estimated.
PI_FLAGS = ("-p", "--mode", "json", "-ne", "-nt", "-nc", "--no-session")

#: The launcher, resolved per platform. The brief names `pi`; on Windows the installed `pi` is a
#: POSIX sh script (`.../pi-node/current/pi`) and `subprocess` without a shell cannot execute it --
#: measured 2026-09-21: `subprocess.run(["pi", "--version"])` -> `FileNotFoundError [WinError 2]`,
#: `subprocess.run(["pi.cmd", "--version"])` -> rc 0, `0.86.1`. The `.cmd` shim execs the same
#: `dist/bundle/cli.js` with the same arguments, so only the launcher differs - and the argv stays
#: a list either way.
PROGRAM = "pi.cmd" if os.name == "nt" else "pi"

#: How long one call may take before its process is killed. A chosen bound, **not** a measurement:
#: the two probe calls took 2,698 ms and 14,013 ms wall, a judgement over a fetched page is
#: longer, and the brief names no number. A call that exceeds it raises; the batch stops.
DEFAULT_TIMEOUT = 180.0

#: How much evidence text may be inlined into one prompt, in characters. **An interpretation, not a
#: source's figure** - but one bounded by a measurement now instead of by arithmetic on a phrase.
#: The first live batch (batch-0001: 15 sites, 61 requests, 2026-09-21) wrote 23 evidence files:
#: median 469 bytes, with a long tail - the largest site's combined evidence was 23,947 characters
#: (Siega Verde), then 13,649 (Hattusas), 8,194 and 8,071. The derivation that stood here before
#: (a "~2,300 input tokens" design point x 4 characters per token) misread what that phrase covered:
#: a bare call is 437 input tokens, and 2,300 described the whole call rather than its evidence, so
#: the bound was set below the real middle of the distribution and refused 2 of 15 sites.
#: **Raised from 32,000 to 64,000 on 2026-09-21, from the recall fixture's own figures** - which is
#: what this comment asks for rather than a fresh guess. Across those 24 sites the combined evidence
#: reached 49,952 characters (Pyramid of Caius Cestius) and 37,339 (Priene Ruins), and a 32,000 bound
#: refused exactly those two **whole**: all five of their fields became unverifiable, including the
#: fields whose decisive sentence sits in the part that would have fitted. 64,000 is the observed
#: maximum plus about a third, the headroom the earlier figure was aiming at, and the fetch stage
#: caps every page at 61,440 bytes, so the input is bounded whatever this value says. A page that
#: does not fit still raises rather than being truncated silently - a judgement made on half a page
#: is a judgement on evidence the model never saw - and that refusal is the sensor: if a later batch
#: trips it, this number gets raised from that batch's own figures rather than from another guess.
MAX_EVIDENCE_CHARS = 64_000

#: The ONE question each stage asks. The finder's is the brief's own frame ("You are the finder in
#: a two-stage factual audit ... You propose; you do not write", `FINDER_BRIEF.md` heading), the
#: reviewer's is its job sentence ("try to refute every single one", `REVIEWER_BRIEF.md` opening).
#: One question per stage is the point: a second question is a second role, and `phase3.model`
#: already spells the two roles `Stage.FINDER` / `Stage.REVIEWER`.
FINDER_QUESTION = (
    "Is the site's stored value for the flagged field wrong, given only the evidence in this "
    "message? Answer yes or no, then name the evidence that decides it in one sentence. "
    "You propose; you do not write."
)
FALSE_ALARMS: tuple[str, ...] = (
    "a round era value on its own - `period_start` is a sort key, and only a value from a different "
    "bucket is an error",
    "`England` / `Scotland` / `Wales` on a UK site, and `civilization` as the stored country copy - "
    "both are project design, not errors",
    "an official UNESCO title such as `Archaeological Site of Olympia` - that is the name, not "
    "prefix clutter",
    "a *less* specific value where the stored one is finer - Wikidata saying 'archaeological site' "
    "does not make 'Temple' wrong",
    "a date on the card that belongs to a named person, or that is only the text's terminus - "
    "neither is a dating of the site",
    "a Wikidata coordinate that is the parent city's, or a distance smaller than the item's own "
    "precision",
    "a border or a missing island in a generalised map - Northern Ireland drawn as `Ireland`, "
    "Crimea, Northern Cyprus, Kosovo, the Baltic",
    "a site of the same name somewhere else - the name *and* the coordinates must both match",
)

#: Which plan item each `FALSE_ALARMS` entry paraphrases, position for position. The plan's 4.3 lists
#: eleven patterns and these eight entries cover all eleven; the numbers live here rather than in the
#: question because the model has never read the plan, and a test reads them back against the plan
#: file so that an added or dropped pattern is loud instead of silent.
FALSE_ALARM_SOURCES: tuple[tuple[str, ...], ...] = (
    ("4.3.1",),
    ("4.3.2", "4.3.4"),
    ("4.3.3",),
    ("4.3.5",),
    ("4.3.7", "4.3.8"),
    ("4.3.9", "4.3.10"),
    ("4.3.11",),
    ("4.3.6",),
)


def _false_alarm_block() -> str:
    """The briefing Phase 3 requires: "must be briefed on the false-alarm patterns in 4.3".

    Kept as data rather than as prose inside the question, so that a test can hold it against the
    plan's own list - `FALSE_ALARM_SOURCES` says which plan item each line covers.
    """
    return "False alarms that are not errors, however wrong they look:\n" + "".join(
        f"- {pattern}\n" for pattern in FALSE_ALARMS
    )


REVIEWER_QUESTION = (
    "A finding claims the stored value is wrong and proposes what to write instead. **Refute it if "
    "either half fails**:\n"
    "\n"
    "1. the reason it gives does not hold - the evidence does not show the stored value wrong; or\n"
    "2. the proposed value is contradicted by the evidence.\n"
    "\n"
    "Use everything you have: the evidence in this message and your own knowledge of the subject. "
    "That the stored text looks weak is **not** by itself a reason to refute - saying so is what "
    "every finding does.\n"
    "\n" + _false_alarm_block() + "\n"
    "Answer with a `WHY:` line and one verdict line, and nothing else:\n"
    "\n"
    "REFUTED: YES | NO | UNRESOLVED\n"
    "\n"
    "* `YES` - one of the two halves fails. Name which on the `WHY:` line, and add a `SOURCE:` line "
    "only if a page in this message is what shows it.\n"
    "* `NO` - both halves hold: the reason stands and the proposed value is not contradicted. Say on "
    "the `WHY:` line what supports it, and write no `SOURCE:` line.\n"
    "* `UNRESOLVED` - neither this message's evidence nor your own knowledge settles one of the two "
    "halves. Say which on the `WHY:` line, and write no `SOURCE:` line.\n"
    "\n"
    "WHY: <one sentence naming the half that fails, or that both hold>\n"
    'SOURCE: <a url that appears in the evidence below> - "<a sentence you copied word for word '
    'from that page>"\n'
    "\n"
    "Write exactly one `REFUTED:` line, unnumbered and unshaded, and write nothing after it: a "
    "numbered answer, or a second verdict line, is read as no verdict at all. A `SOURCE:` line on a "
    "verdict that is not `YES` is an opinion dressed as a citation, and it is read as a problem "
    "rather than as support."
)

#: One question per stage, keyed by the stage enum piece 1 already defines.
STAGE_QUESTION: dict[Stage, str] = {
    Stage.FINDER: FINDER_QUESTION,
    Stage.REVIEWER: REVIEWER_QUESTION,
}

#: Read into every prompt whose site has at least one failed target. It exists because "could not
#: look" and "looked and found nothing" justify different verdicts, and the prompt has to say which
#: one it is holding: a page that was never read is not a page that says nothing. **The wording is
#: mine** - the requirement is piece 4's deliverable C, the sentence is an interpretation of it.
PARTIAL_EVIDENCE_NOTE = (
    "Some evidence targets for this site could not be read; they are listed below with "
    'status="failed" and the reason. A failed target is evidence that was never read - it is '
    "neither confirmation nor a clean bill of health. If your answer depends on a failed target, "
    "answer `unverifiable` and name that target instead of reading the failure as absence of a "
    "defect."
)

#: The first words of an evidence block whose target failed (the full reason follows).
FAILED_TARGET_MARKER = "[failed:"

#: The marker for a target that is not on disk in a *preview* (`allow_absent=True`), where no
#: failure was recorded either: the dry run shows the hole rather than hiding it.
ABSENT_TARGET_MARKER = "[absent:"


class ModelCallFailed(RuntimeError):
    """The call produced no usable, measured answer. Raised, never turned into an empty result."""


class UnreadableStream(ModelCallFailed):
    """Bytes came back, and no single settled measured answer could be read out of them.

    The subclass exists so the two facts a `ModelCallFailed` carries are told apart. A *transport*
    failure - a timeout, a non-zero exit, a process that could not be started - is a fact about the
    run of the process and stops the batch. An *unreadable stream* is a fact about one call's bytes:
    the provider answered (and may have billed), but the stream carries no text, or no usage block,
    or more than one settled assistant usage, so there is nothing to write and nothing to measure.

    Measured 2026-09-21, the mass run over 5,004 sites: 8 calls threw from exactly two sites of this
    class - the empty assistant text (`_assistant_text`) and the stream with more than one settled
    assistant usage (`parse_stream`) - four batches each, and each throw took the whole batch, its
    already-answered calls included, down with it (`output/remediation/logs/mass/batch-0143.judge.log`).
    The judge loops record one of these per call as a named failure and carry on; the transport
    class still propagates. Nothing is retried and no zero-usage ledger line is written: module
    refusal 2 ("It never writes an unmeasured call") is unchanged.
    """


class EvidenceUnusable(ModelCallFailed):
    """The evidence for a site cannot be turned into one bounded prompt (absent, or too large)."""


class EvidenceOverBound(EvidenceUnusable):
    """The site's readable evidence is over `MAX_EVIDENCE_CHARS`, so no bounded prompt exists.

    A class of its own rather than a message a caller has to match, because the two facts need
    different handling and a caller must not be able to confuse them: evidence that is missing with
    **nothing recorded about it** is a hole in the record and stops the batch (`prepare_call` raises
    the parent), while evidence that is **too large to judge** is a fact about the evidence, which
    the discover pass records as that site's own `unverifiable` outcome and carries on past
    (`phase3/discover_stage.py`). `total` and `bound` are the site's own numbers, so a report can
    quote the arithmetic that decided it without parsing this message.
    """

    def __init__(self, *, site_id: str, total: int, bound: int) -> None:
        super().__init__(
            f"{site_id}: the evidence is {total} characters, over the {bound}-character bound "
            "(the design point is ~2,300 input tokens per call). Truncating silently would judge a "
            "page the model never saw; narrow the evidence or raise the bound deliberately."
        )
        self.site_id = site_id
        self.total = total
        self.bound = bound


def pi_argv(
    *,
    program: str = PROGRAM,
    model: str = MODEL,
    thinking: str = THINKING,
) -> list[str]:
    """The exact argv, as a **list**. The prompt is deliberately **not** in it.

    `subprocess` gets this list and no shell, so a shell metacharacter in a prompt (a site name
    with `$(`, `&`, `|` or a quote) is data, not syntax. There is no quoting to get wrong because
    nothing quotes - and because the prompt travels on stdin, it is not limited by the operating
    system's command-line length either (see the module docstring for the measurement).
    """
    return [program, *PI_FLAGS, "--model", model, "--thinking", thinking]


@dataclass(frozen=True)
class Usage:
    """The settled numbers of one call, exactly as the provider reported them."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    #: The provider's own `cost.total`, in USD. The unit is checked, not assumed: the captured
    #: 0.000342 for 2,276 input tokens matches deepseek-v4.1-flash's $0.15/M input
    #: (0.15 x 2276 / 1e6 = 0.000341). No price is ever applied to a count in this module.
    cost_usd: float

    @classmethod
    def from_message_end(cls, usage: Mapping[str, Any], *, source: str) -> Usage:
        """Read `message.usage` of the assistant `message_end`. Every key is required."""
        counts = {
            "input_tokens": _count(usage, "input", source),
            "output_tokens": _count(usage, "output", source),
            "cache_read_tokens": _count(usage, "cacheRead", source),
            "cache_write_tokens": _count(usage, "cacheWrite", source),
            "total_tokens": _count(usage, "totalTokens", source),
        }
        cost = usage.get("cost")
        if not isinstance(cost, dict) or "total" not in cost:
            raise UnreadableStream(
                f"{source}: usage carries no `cost.total` - the provider's own cost is the only "
                "dollar figure this runner records, and it is never computed from a price table"
            )
        reported = cost["total"]
        if not isinstance(reported, (int, float)) or isinstance(reported, bool):
            raise UnreadableStream(f"{source}: cost.total={reported!r} is not a number")
        if reported != reported or reported in (float("inf"), float("-inf")) or reported < 0:
            raise UnreadableStream(f"{source}: cost.total={reported!r} is not a cost")
        return cls(cost_usd=float(reported), **counts)


def _count(usage: Mapping[str, Any], key: str, source: str) -> int:
    value = usage.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UnreadableStream(
            f"{source}: usage.{key}={value!r} is not a token count - token counts are recorded "
            "per call and never estimated, so a call without them is not written"
        )
    return value


def _assistant_text(message: Mapping[str, Any], *, source: str) -> str:
    """`message.content[].text`, joined. An answer of nothing is not an answer."""
    content = message.get("content")
    if not isinstance(content, list):
        raise UnreadableStream(
            f"{source}: assistant message carries content={content!r}, not a list"
        )
    text = "".join(
        part["text"]
        for part in content
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    ).strip()
    if not text:
        raise UnreadableStream(
            f"{source}: the assistant message carries no text - an empty answer is not a result"
        )
    return text


@dataclass(frozen=True)
class ModelAnswer:
    """One settled answer: the text, and the provider's measured usage of it."""

    text: str
    usage: Usage

    @property
    def cost_usd(self) -> float:
        return self.usage.cost_usd


def parse_stream(lines: Iterable[str], *, source: str) -> ModelAnswer:
    """Parse a `--mode json` event stream into the one settled answer in it.

    The settled usage and the text both come from the `message_end` event of the assistant
    message - the event whose `usage` is final. `message_update` events carry partial text and are
    not read: a partial answer is not a result, and a usage that is not settled is not a
    measurement. Any line that is not a JSON object raises (a capture that merged a second stream
    into this one is a shape this parser refuses, not one it guesses about).

    Every refusal here is an `UnreadableStream`: the bytes are in hand and hold no single settled
    measured answer, which is a fact about this one call rather than about the batch.
    """
    settled: list[ModelAnswer] = []
    for lineno, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text:
            raise UnreadableStream(f"{source}:{lineno}: empty line in the event stream")
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnreadableStream(f"{source}:{lineno}: not JSON ({exc}): {text[:120]!r}") from exc
        if not isinstance(event, dict):
            raise UnreadableStream(
                f"{source}:{lineno}: event is {type(event).__name__}, not an object"
            )
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        where = f"{source}:{lineno} assistant message_end"
        usage = message.get("usage")
        if not isinstance(usage, dict):
            raise UnreadableStream(
                f"{where}: no usage block - the call cannot be written as if it were measured"
            )
        settled.append(
            ModelAnswer(
                text=_assistant_text(message, source=where),
                usage=Usage.from_message_end(usage, source=where),
            )
        )
    if not settled:
        raise UnreadableStream(f"{source}: no assistant message_end event - nothing was measured")
    if len(settled) > 1:
        raise UnreadableStream(
            f"{source}: {len(settled)} settled assistant usages in one stream; this runner will "
            "not guess which call was billed"
        )
    return settled[0]


@dataclass(frozen=True)
class ModelCall:
    """One judgement to buy: the stage, the batch, the site and the exact prompt."""

    stage: Stage
    batch_id: str
    site_id: str
    prompt: str
    #: The one field this call judges, or `None` for the finding-driven call whose subject is the
    #: whole site record. The discover pass sets it: it asks one question per (site, field), so the
    #: field is part of the call's identity - it names the answer file (`answer_key`) and the ledger
    #: label, which is what keeps five calls for one site from being written as one.
    field: str | None = None

    def __post_init__(self) -> None:
        if not self.batch_id:
            raise InputError("a model call needs the batch_id it belongs to")
        if not self.site_id:
            raise InputError("a model call needs the site it judges")
        if self.field is not None and not self.field:
            raise InputError(f"{self.site_id}: a field-scoped call needs the field it judges")
        if not self.prompt.strip():
            raise InputError(f"{self.site_id}: a model call needs a prompt")

    @property
    def answer_key(self) -> str:
        """What this call's answer is stored under: the field, or the stage when none is set.

        `fetch_stage.EvidenceStore` is keyed by `(site, feature)` and refuses to put different
        bytes over a recorded file, so a stage-keyed answer would make a site's second field a
        conflict with its first. Keying by field is what makes one answer per (site, field).
        """
        return self.field or self.stage.value

    @property
    def label(self) -> str:
        """`<site_id>/<field-or-stage>`, the fetch stage's `<site>/<feature>` label shape."""
        return f"{self.site_id}/{self.answer_key}"


@runtime_checkable
class ModelRunner(Protocol):
    """The seam. The real driver is `PiRunner`; tests pass a scripted one and never spend money."""

    def run(self, call: ModelCall) -> ModelAnswer:
        """Answer `call`, or raise `ModelCallFailed`."""
        ...


class PiRunner:
    """The real driver: one Pi process per call, argv list, no shell, no retry."""

    def __init__(
        self,
        *,
        program: str = PROGRAM,
        timeout: float = DEFAULT_TIMEOUT,
        model: str = MODEL,
        thinking: str = THINKING,
        cwd: Path | None = None,
    ) -> None:
        if timeout <= 0:
            raise InputError(f"timeout must be > 0 seconds, got {timeout}")
        self.program = program
        self.timeout = timeout
        self.model = model
        self.thinking = thinking
        self.cwd = cwd

    def argv(self) -> list[str]:
        """The exact argv this runner would hand to `subprocess`. The prompt is on stdin."""
        return pi_argv(program=self.program, model=self.model, thinking=self.thinking)

    def run(self, call: ModelCall) -> ModelAnswer:
        """Run one Pi process and return its settled answer.

        `subprocess.run(..., timeout=)` kills the child and re-raises, so a hung process cannot
        hold the batch; the kill is turned into `ModelCallFailed` here.
        """
        argv = self.argv()
        try:
            proc = subprocess.run(  # noqa: S603 - argv list, shell=False, no string ever built
                argv,
                # The prompt goes on **stdin**, UTF-8 encoded, so it is never an argv element:
                # Windows caps a `cmd.exe` command line near 8,191 characters and a prompt
                # carrying evidence is far longer (the module docstring records the measurement).
                # Encoded explicitly so the child reads the same bytes on every platform.
                input=call.prompt.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout,
                shell=False,
                check=False,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise ModelCallFailed(
                f"{call.label}: {argv[0]} did not answer within {self.timeout}s; the process was "
                "killed and the batch stops here (no retry: a retry doubles the charge invisibly)"
            ) from exc
        except OSError as exc:
            raise ModelCallFailed(f"{call.label}: {argv[0]!r} could not be started: {exc}") from exc
        if proc.returncode != 0:
            # stderr is decoded leniently *for this message only*; no result is read from it.
            tail = proc.stderr.decode("utf-8", errors="replace")[-800:]
            raise ModelCallFailed(
                f"{call.label}: {argv[0]} exited {proc.returncode}; stderr tail: {tail!r}"
            )
        try:
            stdout = proc.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnreadableStream(
                f"{call.label}: stdout is not UTF-8 ({exc}); the event stream is unreadable"
            ) from exc
        return parse_stream(stdout.splitlines(), source=f"{call.label} stdout")


@dataclass(frozen=True)
class Prompt:
    """The two blocks of one prompt: the stage's fixed question, and this site's material."""

    stage: Stage
    system: str  #: the ONE question this stage asks
    user: str  #: the site record plus the evidence piece 2 collected

    @property
    def chars(self) -> int:
        return len(self.system) + len(self.user)

    def render(self) -> str:
        """The exact text that is the last argv element. Both blocks travel in it: the transport
        is one prompt argument per process (`pi ... <prompt>`), so the question is a labelled
        block rather than a system message."""
        return f"<question>\n{self.system}\n</question>\n\n{self.user}\n"


@dataclass(frozen=True)
class EvidenceExcerpt:
    """One evidence file as it goes into the prompt. `text is None` when it could not be read.

    `failure` is set only when the fetch stage recorded that this target failed: it carries the
    reason the file is not there, so the prompt says which question it cannot answer instead of
    presenting an unread page as an empty one.
    """

    feature: str
    url: str
    path: Path
    text: str | None
    failure: str | None = None

    @property
    def chars(self) -> int:
        return len(self.text) if self.text is not None else 0

    @property
    def present(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class PreparedCall:
    """A call and the evidence it carries. Built before any process starts."""

    call: ModelCall
    excerpts: list[EvidenceExcerpt]


def _site_block(site: Mapping[str, Any], site_id: str) -> str:
    """The stored record: what the worklist says the row holds, for the fields it flagged."""
    name = site.get("name")
    if not isinstance(name, str) or not name:
        raise InputError(f"{site_id}: site record carries no name")
    findings = site.get("findings")
    if not isinstance(findings, list) or not findings:
        raise InputError(f"{site_id}: site record carries no findings")
    rows = []
    for finding in findings:
        test_id = finding.get("test_id")
        field = finding.get("field")
        if not test_id or not field:
            raise InputError(f"{site_id}: a finding carries no test_id/field: {dict(finding)!r}")
        rows.append(
            f'<finding test_id="{test_id}" field="{field}" '
            f'severity="{finding.get("severity", "")}" '
            f'current_value="{json.dumps(finding.get("current_value"), ensure_ascii=False)}">'
            f"{finding.get('note', '')}</finding>"
        )
    return f'<site id="{site_id}" name="{name}">\n' + "\n".join(rows) + "\n</site>"


def evidence_block(excerpts: list[EvidenceExcerpt]) -> str:
    blocks = []
    for excerpt in excerpts:
        if excerpt.text is not None:
            status, body = "present", excerpt.text
        elif excerpt.failure is not None:
            status = "failed"
            body = (
                f"{FAILED_TARGET_MARKER} {excerpt.failure}] This target was never read, so it "
                "shows nothing about the stored value either way."
            )
        else:
            status = "absent"
            body = (
                f"{ABSENT_TARGET_MARKER} no evidence file at {excerpt.path} - a live call refuses "
                "to judge evidence that is not on disk; run `phase3-run fetch --live` first]"
            )
        blocks.append(
            f'<evidence feature="{excerpt.feature}" status="{status}" url="{excerpt.url}">\n'
            f"{body}\n</evidence>"
        )
    return "\n".join(blocks)


def failed_target_block(excerpts: list[EvidenceExcerpt]) -> str:
    """The failed targets, named, or "" when every target answered."""
    failed = [e for e in excerpts if e.failure is not None]
    if not failed:
        return ""
    rows = "".join(
        f'<failed_target feature="{e.feature}" url="{e.url}" reason="{e.failure}" />\n'
        for e in failed
    )
    return f"<failed_targets>\n{PARTIAL_EVIDENCE_NOTE}\n{rows}</failed_targets>\n"


#: The search stage's report, written beside `fetch.json` in the same batch directory and in the same
#: `sites[].outcomes[].failure` shape (`phase3/search_stage.py`).
SEARCH_REPORT_NAME = "search.json"


def read_fetch_failures(path: Path) -> dict[str, dict[str, str]]:
    """`site_id -> {feature: why it has no evidence}`, from the fetch report and the search report.

    `path` is the batch's `fetch.json`; the search stage's `search.json` in the same directory is read
    too, because a failed search is the same fact as a failed fetch - a target that was asked and
    bought nothing - and every caller that reads the one must see the other. The two never share a
    feature (`minimax_search.*` is the search stage's alone), so the result is their union.

    An absent report means that stage never ran live, and it contributes nothing: no target's absence
    is explained by it, so every such target still raises at prompt time. A report that **exists** but
    is unreadable, or whose shape is not the one its stage writes, raises - an unreadable record must
    not look like a clean one.
    """
    failures = _read_outcome_failures(path)
    for site_id, rows in _read_outcome_failures(path.with_name(SEARCH_REPORT_NAME)).items():
        mine = failures.setdefault(site_id, {})
        clash = sorted(set(mine) & set(rows))
        if clash:
            raise InputError(f"{path.parent}: {site_id} has failures for {clash} in both reports")
        mine.update(rows)
    return failures


def _read_outcome_failures(path: Path) -> dict[str, dict[str, str]]:
    """One report's `site_id -> {feature: failure}`. See `read_fetch_failures`."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{path}: the report is not JSON: {exc}") from exc
    sites = payload.get("sites") if isinstance(payload, dict) else None
    if not isinstance(sites, list):
        raise InputError(f"{path}: the report carries no `sites` list: {payload!r}")
    failures: dict[str, dict[str, str]] = {}
    for site in sites:
        if not isinstance(site, dict) or not site.get("site_id"):
            raise InputError(f"{path}: a report entry carries no site_id: {site!r}")
        rows = site.get("outcomes")
        if not isinstance(rows, list):
            raise InputError(f"{path}: {site['site_id']} carries no `outcomes` list: {site!r}")
        for row in rows:
            if not isinstance(row, dict) or row.get("failure") is None:
                continue
            feature = row.get("feature")
            if not isinstance(feature, str) or not feature:
                raise InputError(f"{path}: a failed outcome carries no feature: {row!r}")
            failures.setdefault(str(site["site_id"]), {})[feature] = str(row["failure"])
    return failures


def evidence_excerpts(
    *,
    site_id: str,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    allow_absent: bool = False,
    failures: Mapping[str, str] | None = None,
) -> list[EvidenceExcerpt]:
    """The site's evidence, read once: one excerpt per target `fetch_stage` built for it, then one per
    page the site's searches found (`_search_excerpts`; a site without `search_fields` has none).

    Extracted from `prepare_call` for the discover pass, which builds one prompt per (site, field)
    from the same excerpts (`phase3/discover_stage.py`): the guard below is the thing that must not
    have two spellings. A file that is not on disk is named by `failures` **when the fetch stage
    recorded a failure for that feature**, and refused otherwise - evidence missing with nothing
    recorded about it is a hole in the record, and the model is never asked to judge a page nobody
    has an account of. `allow_absent` marks it for a preview instead of raising.
    """
    recorded = failures or {}
    excerpts: list[EvidenceExcerpt] = []
    for target in F.targets_for_site(site):
        path = store.path_for(target.site_id, target.feature)
        failure: str | None = None
        if path.exists():
            text = path.read_text(encoding="utf-8")
        elif target.feature in recorded:
            text = None
            failure = recorded[target.feature]
        elif allow_absent:
            text = None
        else:
            raise EvidenceUnusable(
                f"{site_id}: the evidence file for {target.feature} is not at {path}, and the "
                "fetch report records no failure for it; the model is never asked to judge "
                "evidence that is not on disk"
            )
        excerpts.append(
            EvidenceExcerpt(
                feature=target.feature, url=target.url, path=path, text=text, failure=failure
            )
        )
    excerpts.extend(
        _search_excerpts(
            site_id=site_id,
            site=site,
            store=store,
            recorded=recorded,
            allow_absent=allow_absent,
            taken={excerpt.url for excerpt in excerpts},
        )
    )
    return excerpts


def _search_excerpts(
    *,
    site_id: str,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    recorded: Mapping[str, str],
    allow_absent: bool,
    taken: set[str],
) -> list[EvidenceExcerpt]:
    """One excerpt per page the site's searches found, after the fetched targets (the search lane).

    A site without `search_fields` buys no search (`search_evidence.search_slots` is empty), so the
    mass run's excerpts - and every prompt built from them - are exactly what they were, and a site
    that only reruns fields (the gap run's `rerun_fields` without `search_fields`) is judged on its
    fetched targets alone: no search file is required of it, because none was ever bought.

    For a site that has searches, each one is on disk, or recorded as failed by the search stage, or
    (in a preview) absent; anything else raises, the same rule as a fetched target. A stored hit
    becomes one excerpt: the url is the hit's link, the text is `search_evidence.hit_text` (plain
    text, so a quote copied from a snippet passes `discover_stage.quote_occurs`). Hits on our own
    site or on a blocked host are left out (`search_evidence.excluded_because`).

    The same url found by two searches becomes **one** excerpt carrying both texts: the citation
    check reads the pages as a dict keyed by url (`discover_stage.pages_from_excerpts`), and a second
    excerpt under the same key would replace the first, failing an honest quote from it. For the
    same reason a hit whose url is already a fetched target's raises instead of being merged into a
    page of a different kind.
    """
    merged: dict[str, tuple[list[str], list[str], Path]] = {}
    unread: list[EvidenceExcerpt] = []
    for slot in SE.search_slots(site):
        path = store.path_for(site_id, slot.feature)
        if not path.exists():
            if slot.feature in recorded:
                failure: str | None = recorded[slot.feature]
            elif allow_absent:
                failure = None
            else:
                raise EvidenceUnusable(
                    f"{site_id}: the search {slot.feature} is not at {path}, and the search report "
                    "records no failure for it; the model is never asked to judge evidence that "
                    "is not on disk"
                )
            unread.append(
                EvidenceExcerpt(
                    feature=slot.feature,
                    url=SE.SEARCH_TARGET_URL,
                    path=path,
                    text=None,
                    failure=failure,
                )
            )
            continue
        for hit in SE.read_record(path).hits:
            if SE.excluded_because(hit.url) is not None:
                continue
            if hit.url in taken:
                raise EvidenceUnusable(
                    f"{site_id}: the search {slot.feature} found {hit.url}, which is already a "
                    "fetched target of this site; one url cannot be two pages in the citation check"
                )
            features, texts, _ = merged.setdefault(hit.url, ([], [], path))
            if slot.feature not in features:
                features.append(slot.feature)
            text = SE.hit_text(hit)
            if text not in texts:
                texts.append(text)
    pages = [
        EvidenceExcerpt(
            feature="+".join(features), url=url, path=path, text="\n".join(texts), failure=None
        )
        for url, (features, texts, path) in merged.items()
    ]
    return pages + unread


def check_evidence_bound(site_id: str, excerpts: Iterable[EvidenceExcerpt]) -> None:
    """Refuse to build a prompt over `MAX_EVIDENCE_CHARS`, quoting the site's own arithmetic.

    Shared with the discover pass, which turns `EvidenceOverBound` into that site's own outcome
    instead of letting it end the batch; the comparison itself has one spelling, here.
    """
    total = sum(excerpt.chars for excerpt in excerpts)
    if total > MAX_EVIDENCE_CHARS:
        raise EvidenceOverBound(site_id=site_id, total=total, bound=MAX_EVIDENCE_CHARS)


def prepare_call(
    *,
    batch_id: str,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    stage: Stage,
    allow_absent: bool = False,
    failures: Mapping[str, str] | None = None,
) -> PreparedCall:
    """Build one site's prompt: its record, plus the evidence files piece 2 stored.

    `allow_absent` exists for `run judge` without `--live`: the preview renders the call a batch
    *would* make, and marks each evidence file that is not on disk yet. With `allow_absent=False`
    (every live path) an absent file **raises** - unless `failures` explains it: `failures` is
    `{feature: reason}`, read back from the batch's own `fetch.json` via `read_fetch_failures`, and
    a target named there was asked and failed, so the prompt carries that instead of guessing.
    Evidence missing with no such record is still refused: the model is never asked to judge a
    page that nobody has an account of.

    The evidence selection and the size guard are `evidence_excerpts` and `check_evidence_bound`,
    so the discover pass's per-(site, field) prompts go through the same two calls.
    """
    site_id = str(site.get("site_id") or "")
    if not site_id:
        raise InputError(f"batch {batch_id}: a site record carries no site_id")
    excerpts = evidence_excerpts(
        site_id=site_id, site=site, store=store, allow_absent=allow_absent, failures=failures
    )
    check_evidence_bound(site_id, excerpts)
    user = "\n".join(
        [_site_block(site, site_id), evidence_block(excerpts), failed_target_block(excerpts)]
    )
    prompt = Prompt(stage=stage, system=STAGE_QUESTION[stage], user=user)
    return PreparedCall(
        call=ModelCall(stage=stage, batch_id=batch_id, site_id=site_id, prompt=prompt.render()),
        excerpts=excerpts,
    )


def prepare_batch(
    *,
    batch: Mapping[str, Any],
    store: F.EvidenceStore,
    stage: Stage,
    allow_absent: bool = False,
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> list[PreparedCall]:
    """One prepared call per site of the batch, in batch order.

    `failures` is `read_fetch_failures`'s whole result (keyed by site), not one site's slice.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    recorded = failures or {}
    return [
        prepare_call(
            batch_id=batch_id,
            site=site,
            store=store,
            stage=stage,
            allow_absent=allow_absent,
            failures=recorded.get(str(site.get("site_id") or "")),
        )
        for site in sites
    ]


@dataclass(frozen=True)
class JudgedCall:
    """One answered call: the answer, and whether its file was new (`wrote=False` = same bytes)."""

    answer: ModelAnswer
    wrote: bool


def judge_site(
    *,
    prepared: PreparedCall,
    runner: ModelRunner,
    ledger: L.Ledger,
    answers: F.EvidenceStore,
) -> JudgedCall:
    """One model call, one ledger line, one stored answer - in that order, ledger before store.

    The line goes down as soon as the call is answered, so a crash after it leaves the *money*
    visible and only the answer missing. The stored answer keeps the raw text: the numbers are in
    the ledger, the words are in the file, and neither is a second spelling of the other.

    A question whose answer is already on disk is not asked again. The store's own rule - existence
    is the record - belongs here as much as in the fetch stage, and it belongs here *before* the
    call: a re-run of a batch whose answers survive would pay for a second answer to a settled
    question, and `write` refuses to overwrite the first one with different bytes, so the batch
    would end on an `EvidenceConflict` instead of a verdict. That is measured, not imagined: three
    consecutive mass-run batches died exactly there on 2026-09-21 and tripped the circuit breaker.
    Nothing is appended to the ledger either, because asking is what a ledger line records and
    nothing was asked; the judgement carries the stored answer's own length with zero usage, so a
    reuse reads as `wrote=False` and a cost of 0 in `model.json`. Deleting the answer file (with the
    evidence file it was judged against) is how a human asks that one question again.
    """
    call = prepared.call
    if answers.exists(call.site_id, call.answer_key):
        stored_path = answers.path_for(call.site_id, call.answer_key)
        return JudgedCall(
            answer=ModelAnswer(
                text=stored_path.read_text(encoding="utf-8"),
                usage=Usage(
                    input_tokens=0,
                    output_tokens=0,
                    cache_read_tokens=0,
                    cache_write_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                ),
            ),
            wrote=False,
        )
    answer = runner.run(call)
    ledger.append(
        L.Entry(
            kind=L.LedgerKind.MODEL_CALL,
            stage=call.stage,
            batch_id=call.batch_id,
            label=call.label,
            model=MODEL,
            input_tokens=answer.usage.input_tokens,
            output_tokens=answer.usage.output_tokens,
            cache_read_tokens=answer.usage.cache_read_tokens,
            cache_write_tokens=answer.usage.cache_write_tokens,
            cost_usd=answer.usage.cost_usd,
        )
    )
    # The fetch stage's store, reused deliberately: one file per (site, feature) there, one file
    # per (site, field-or-stage) here, and both refuse to overwrite recorded bytes with different
    # ones. `call.answer_key` is the field for a discover call, so five calls for one site leave
    # five files instead of five writes to one.
    stored = answers.write(
        site_id=call.site_id, feature=call.answer_key, body=answer.text.encode("utf-8")
    )
    return JudgedCall(answer=answer, wrote=stored.wrote)


@dataclass
class SiteJudgement:
    """What one call cost and what it left on disk. Counts, not prose."""

    site_id: str
    label: str
    answer_chars: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    wrote: bool
    #: The field this call judged, or `None` for a per-site call (`ModelCall.field`). Carried here
    #: so a report reader can count calls per field without parsing `label`.
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class SkippedSite:
    """A site that bought **no model call**, and why. Never an empty result: a record with a reason.

    `findings` are the `unverifiable` verdicts this site's record now carries: one per census
    finding, because `phase3.model.Finding` is one judgement about one field of one site and the
    verdict for each of them is the same - the evidence cannot settle it. No answer was parsed
    here: there was no call to parse.
    """

    site_id: str
    reason: str
    findings: list[M.Finding] = field(default_factory=list)
    #: The one field whose call was not bought, or `None` when the whole site was skipped
    #: (`ModelCall.field`). The discover pass asks one question per (site, field), so its skips are
    #: per field too: a field whose evidence never arrived is recorded on its own.
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "field": self.field,
            "reason": self.reason,
            "findings": [json.loads(f.to_json()) for f in self.findings],
        }


def unverifiable_findings(site: Mapping[str, Any], *, site_id: str, reason: str) -> list[M.Finding]:
    """One `Verdict.UNVERIFIABLE` finding per census finding of a site no evidence reached.

    `defect` is derived from the verdict (`model.Finding.defect`), so these can never be read as
    "no defect found": they say the question was not answered, and the reason is in `note`.
    """
    findings: list[M.Finding] = []
    rows = site.get("findings")
    if not isinstance(rows, list) or not rows:
        raise InputError(f"{site_id}: site record carries no findings")
    for row in rows:
        test_id = row.get("test_id")
        field_name = row.get("field")
        severity = row.get("severity")
        if not test_id or not field_name or not severity:
            raise InputError(
                f"{site_id}: a finding carries no test_id/field/severity: {dict(row)!r} - an "
                "unverifiable verdict is recorded per finding, so one it cannot name is a record "
                "this runner will not invent"
            )
        findings.append(
            M.Finding(
                site_id=site_id,
                field=str(field_name),
                verdict=M.Verdict.UNVERIFIABLE,
                severity=M.Severity(str(severity)),
                test_id=str(test_id),
                current_value=row.get("current_value"),
                note=reason,
            )
        )
    return findings


@dataclass(frozen=True)
class FailedCall:
    """One call whose stream could not be read as a single settled measured answer: a named hole.

    Recorded beside the judgements so the batch's `model.json` carries it - the `reason`, the
    `site_id` and the `field` - and deliberately **neither a verdict nor a proposed value**. There
    was no answer, so a verdict or a proposal here would be an invented finding, which is the one
    thing this record exists to prevent.

    It is not a ledger line either. The provider may have billed a stream that came back unreadable,
    but no usage was measured, so a line could only carry invented zeros - which is what
    `phase3.ledger` refuses (module refusal 2, "It never writes an unmeasured call"). A retry has the
    same objection from the other side (refusal 3: a retry doubles the charge invisibly). So the hole
    is written down instead, in the artefact that has a word for it.
    """

    site_id: str
    field: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "field": self.field, "reason": self.reason}


#: The exact keys a named failure carries. `mass_run.batch_state` counts a row only when its key set
#: is this one, so a failure record that grew a `verdict` or a `proposed` value is refused rather
#: than read as settled: "a truncated artefact is not evidence" applies to this list as well.
NAMED_FAILURE_KEYS = frozenset({"site_id", "field", "reason"})


def is_named_failure(row: Any) -> bool:
    """True when `row` is a well-formed named failure, and therefore carries no verdict.

    Read by `mass_run.batch_state`, which must count a call the stream swallowed as settled - that
    call **was** a call - without letting *any* row be counted. Hence the exact key set rather than
    "whatever the list holds": an entry that cannot be located (empty `site_id`), cannot be named
    (`field` neither a string nor `None`), carries no reason, or carries a key this shape does not
    have, is not a named failure.
    """
    if not isinstance(row, dict) or set(row) != NAMED_FAILURE_KEYS:
        return False
    if not isinstance(row.get("site_id"), str) or not row["site_id"]:
        return False
    if row.get("field") is not None and not isinstance(row.get("field"), str):
        return False
    return isinstance(row.get("reason"), str) and bool(row["reason"])


@dataclass
class BatchModelReport:
    """One batch's model stage. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    stage: Stage
    site_ids: list[str]
    judgements: list[SiteJudgement]
    #: Sites that bought no call, each with the reason and the `unverifiable` findings they now
    #: carry. Recorded in the report, **not** in the ledger: the ledger's line kinds are
    #: measurements (a fetch, a model call), and a site that spent nothing has no measurement to
    #: write - a zero-token `model_call` line would be a fabricated one. This is the report line.
    skipped: list[SkippedSite] = field(default_factory=list)
    #: Calls that were bought and came back as an unreadable stream, one `FailedCall` each. The
    #: third outcome beside "judged" and "bought no call": the call happened, the answer did not,
    #: and the batch continues past it. Written to `model.json` so a later reader - a human, the
    #: mass runner's state check - can see which (site, field) pairs are holes instead of counting
    #: answers and guessing.
    failures: list[FailedCall] = field(default_factory=list)

    @property
    def calls(self) -> int:
        """Every call the batch made: the judged answers plus the named holes.

        A failed call **was** a call - the provider was asked and may have charged for it - so it is
        counted here rather than hidden, and `mass_run.batch_state` needs that count to add up
        (`len(judgements) + len(failures)`). It is deliberately not counted as money: with no usage
        block there is no measured `cost_usd`, and a zero would be a fabricated figure (refusal 2).
        """
        return len(self.judgements) + len(self.failures)

    @property
    def unverifiable(self) -> int:
        return sum(len(s.findings) for s in self.skipped)

    @property
    def input_tokens(self) -> int:
        return sum(j.input_tokens for j in self.judgements)

    @property
    def output_tokens(self) -> int:
        return sum(j.output_tokens for j in self.judgements)

    @property
    def cost_usd(self) -> float:
        """The sum of the provider's own per-call figures. Not a price applied to a count."""
        return sum(j.cost_usd for j in self.judgements)

    def to_json(self) -> str:
        payload = {
            "batch_id": self.batch_id,
            "stage": self.stage.value,
            "sites": self.site_ids,
            "judgements": [j.to_dict() for j in self.judgements],
            "skipped": [s.to_dict() for s in self.skipped],
            "failures": [f.to_dict() for f in self.failures],
            "totals": {
                "calls": self.calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": self.cost_usd,
                "unverifiable_findings": self.unverifiable,
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def write_report(path: Path, report: BatchModelReport) -> None:
    """Write the batch report. Same shape as the fetch stage's report file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")


def judge_batch(
    *,
    batch: Mapping[str, Any],
    runner: ModelRunner,
    store: F.EvidenceStore,
    answers: F.EvidenceStore,
    ledger: L.Ledger,
    stage: Stage,
    failures: Mapping[str, Mapping[str, str]] | None = None,
) -> BatchModelReport:
    """Judge every site of the batch: one call, one ledger line, one stored answer per **judged** site.

    A site with no evidence on disk at all is not judged: it is recorded as `unverifiable` with the
    reason (`failures` names the targets that failed; a site whose findings buy no target at all is
    recorded as such), and no process is started.

    A call whose stream comes back unreadable is recorded as a `FailedCall` and the batch carries on
    to the next site. That call was bought and produced no answer, so it is recorded - `site_id`,
    `field`, the reason, no verdict - rather than retried or charged at zero. The rest of the batch is
    untouched by it: before 2026-09-21 one such call threw out of this loop and took every answer
    already written down with it (`output/remediation/logs/mass/batch-0143.judge.log`).

    Nothing else is caught: a call that could not be *made* - a timeout, a non-zero exit, a process
    that would not start, all plain `ModelCallFailed` - propagates, so a batch that could not be
    measured is reported as failed rather than as a smaller batch (`phase3.model.StageResult` has the
    same rule). A re-run re-answers every site and writes a second line per call: the second charge
    is then visible in the ledger instead of hidden behind an invisible retry.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    prepared = prepare_batch(batch=batch, store=store, stage=stage, failures=failures)
    by_id = {
        str(site.get("site_id") or ""): site
        for site in (batch.get("sites") or [])
        if isinstance(site, dict)
    }
    judgements: list[SiteJudgement] = []
    skipped: list[SkippedSite] = []
    named_failures: list[FailedCall] = []
    for item in prepared:
        site_id = item.call.site_id
        if not any(e.present for e in item.excerpts):
            reason = no_evidence_reason(item)
            skipped.append(
                SkippedSite(
                    site_id=site_id,
                    reason=reason,
                    findings=unverifiable_findings(by_id[site_id], site_id=site_id, reason=reason),
                )
            )
            continue
        try:
            judged = judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)
        except UnreadableStream as exc:
            named_failures.append(
                FailedCall(site_id=site_id, field=item.call.field, reason=str(exc))
            )
            continue
        usage = judged.answer.usage
        judgements.append(
            SiteJudgement(
                site_id=site_id,
                label=item.call.label,
                answer_chars=len(judged.answer.text),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=usage.cost_usd,
                wrote=judged.wrote,
                field=item.call.field,
            )
        )
    return BatchModelReport(
        batch_id=batch_id,
        stage=stage,
        site_ids=[item.call.site_id for item in prepared],
        judgements=judgements,
        skipped=skipped,
        failures=named_failures,
    )


def no_evidence_reason(item: PreparedCall) -> str:
    """Why no call was bought for this site. Two different facts, never one blurry sentence."""
    failed = [e for e in item.excerpts if e.failure is not None]
    if not failed:
        return (
            "the site's findings buy no evidence target, so there is nothing this stage could "
            "judge; recorded as unverifiable rather than answered from no evidence"
        )
    detail = "; ".join(f"{e.feature}: {e.failure}" for e in failed)
    return (
        f"no evidence file was read for this site (no model call bought): {detail}. The evidence "
        "cannot settle the stored value, so every finding is recorded unverifiable"
    )

"""Stage "model" of the Phase-3 runner: one non-interactive Pi process per judgement.

The transport is decided and measured, not chosen here. A Pi process in `--mode json` is the
model driver, invoked from an argv list:

    pi -p --mode json -ne -nt -nc --no-session --model opencode-go/deepseek-v4.1-flash
       --thinking off <prompt>

* `-p`          one non-interactive run, no TUI.
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

What this module does not do, stated so it is not mistaken for covered: it does not parse the
model's answer into `phase3.model.Finding` records (that is the next piece - here the answer is
stored verbatim as bytes, one file per `(site, stage)`), and it does not judge `stopReason`: a
`length`-truncated answer would be recorded like any other. Both are named in
`output/remediation/phase3_runner/PIECE3.md`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Dual use: `python -m phase3.model_stage` and `python scripts/remediation/phase3/model_stage.py`.
# The package is not installed, so the parent directory must be importable first (same shim as
# `run.py` and `fetch_stage.py`).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402  - the evidence this stage reads
from phase3 import ledger as L  # noqa: E402
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

#: How much evidence text may be inlined into one prompt, in characters. **An interpretation, not
#: a measurement**, and the only number here read off a phrase: the brief sets the design point of
#: this whole transport at "~2,300 input tokens", and 2,300 x 4 characters per token = 9,200. A
#: page that does not fit raises rather than being truncated silently - a judgement made on half a
#: page is a judgement on evidence the model never saw.
MAX_EVIDENCE_CHARS = 2300 * 4

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
REVIEWER_QUESTION = (
    "Can the finder's finding for this site be refuted against the evidence in this message? "
    "Name the single claim that fails, or say that none did. Try to break every finding."
)

#: One question per stage, keyed by the stage enum piece 1 already defines.
STAGE_QUESTION: dict[Stage, str] = {
    Stage.FINDER: FINDER_QUESTION,
    Stage.REVIEWER: REVIEWER_QUESTION,
}


class ModelCallFailed(RuntimeError):
    """The call produced no usable, measured answer. Raised, never turned into an empty result."""


class EvidenceUnusable(ModelCallFailed):
    """The evidence for a site cannot be turned into one bounded prompt (absent, or too large)."""


def pi_argv(
    prompt: str,
    *,
    program: str = PROGRAM,
    model: str = MODEL,
    thinking: str = THINKING,
) -> list[str]:
    """The exact argv, as a **list**. Nothing here is ever a command line string.

    `subprocess` gets this list and no shell, so a shell metacharacter in a prompt (a site name
    with `$(`, `&`, `|` or a quote) is data, not syntax. There is no quoting to get wrong because
    nothing quotes.
    """
    return [program, *PI_FLAGS, "--model", model, "--thinking", thinking, prompt]


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
            raise ModelCallFailed(
                f"{source}: usage carries no `cost.total` - the provider's own cost is the only "
                "dollar figure this runner records, and it is never computed from a price table"
            )
        reported = cost["total"]
        if not isinstance(reported, (int, float)) or isinstance(reported, bool):
            raise ModelCallFailed(f"{source}: cost.total={reported!r} is not a number")
        if reported != reported or reported in (float("inf"), float("-inf")) or reported < 0:
            raise ModelCallFailed(f"{source}: cost.total={reported!r} is not a cost")
        return cls(cost_usd=float(reported), **counts)


def _count(usage: Mapping[str, Any], key: str, source: str) -> int:
    value = usage.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ModelCallFailed(
            f"{source}: usage.{key}={value!r} is not a token count - token counts are recorded "
            "per call and never estimated, so a call without them is not written"
        )
    return value


def _assistant_text(message: Mapping[str, Any], *, source: str) -> str:
    """`message.content[].text`, joined. An answer of nothing is not an answer."""
    content = message.get("content")
    if not isinstance(content, list):
        raise ModelCallFailed(
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
        raise ModelCallFailed(
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
    """
    settled: list[ModelAnswer] = []
    for lineno, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text:
            raise ModelCallFailed(f"{source}:{lineno}: empty line in the event stream")
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelCallFailed(f"{source}:{lineno}: not JSON ({exc}): {text[:120]!r}") from exc
        if not isinstance(event, dict):
            raise ModelCallFailed(
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
            raise ModelCallFailed(
                f"{where}: no usage block - the call cannot be written as if it were measured"
            )
        settled.append(
            ModelAnswer(
                text=_assistant_text(message, source=where),
                usage=Usage.from_message_end(usage, source=where),
            )
        )
    if not settled:
        raise ModelCallFailed(f"{source}: no assistant message_end event - nothing was measured")
    if len(settled) > 1:
        raise ModelCallFailed(
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

    def __post_init__(self) -> None:
        if not self.batch_id:
            raise InputError("a model call needs the batch_id it belongs to")
        if not self.site_id:
            raise InputError("a model call needs the site it judges")
        if not self.prompt.strip():
            raise InputError(f"{self.site_id}: a model call needs a prompt")

    @property
    def label(self) -> str:
        """`<site_id>/<stage>`, the fetch stage's `<site>/<feature>` label shape."""
        return f"{self.site_id}/{self.stage.value}"


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

    def argv(self, prompt: str) -> list[str]:
        """The exact argv this runner would hand to `subprocess`."""
        return pi_argv(prompt, program=self.program, model=self.model, thinking=self.thinking)

    def run(self, call: ModelCall) -> ModelAnswer:
        """Run one Pi process and return its settled answer.

        `subprocess.run(..., timeout=)` kills the child and re-raises, so a hung process cannot
        hold the batch; the kill is turned into `ModelCallFailed` here.
        """
        argv = self.argv(call.prompt)
        try:
            proc = subprocess.run(  # noqa: S603 - argv list, shell=False, no string ever built
                argv,
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
            raise ModelCallFailed(
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
    """One evidence file as it goes into the prompt. `text is None` only in a dry run."""

    feature: str
    url: str
    path: Path
    text: str | None

    @property
    def chars(self) -> int:
        return len(self.text) if self.text is not None else 0


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


def _evidence_block(excerpts: list[EvidenceExcerpt]) -> str:
    blocks = []
    for excerpt in excerpts:
        if excerpt.text is None:
            body = (
                f"[absent: no evidence file at {excerpt.path} - a live call refuses to judge "
                "evidence that is not on disk; run `phase3-run fetch --live` first]"
            )
        else:
            body = excerpt.text
        blocks.append(
            f'<evidence feature="{excerpt.feature}" url="{excerpt.url}">\n{body}\n</evidence>'
        )
    return "\n".join(blocks)


def prepare_call(
    *,
    batch_id: str,
    site: Mapping[str, Any],
    store: F.EvidenceStore,
    stage: Stage,
    allow_absent: bool = False,
) -> PreparedCall:
    """Build one site's prompt: its record, plus the evidence files piece 2 stored.

    `allow_absent` exists for `run judge` without `--live`: the preview renders the call a batch
    *would* make, and marks each evidence file that is not on disk yet. With `allow_absent=False`
    (every live path) an absent file raises - the model must not be asked to judge evidence that
    is not there.
    """
    site_id = str(site.get("site_id") or "")
    if not site_id:
        raise InputError(f"batch {batch_id}: a site record carries no site_id")
    excerpts: list[EvidenceExcerpt] = []
    total = 0
    for target in F.targets_for_site(site):
        path = store.path_for(target.site_id, target.feature)
        if path.exists():
            text = path.read_text(encoding="utf-8")
        elif allow_absent:
            text = None
        else:
            raise EvidenceUnusable(
                f"{site_id}: the evidence file for {target.feature} is not at {path}; the model is "
                "never asked to judge evidence that is not on disk"
            )
        total += len(text) if text is not None else 0
        excerpts.append(
            EvidenceExcerpt(feature=target.feature, url=target.url, path=path, text=text)
        )
    if total > MAX_EVIDENCE_CHARS:
        raise EvidenceUnusable(
            f"{site_id}: the evidence is {total} characters, over the {MAX_EVIDENCE_CHARS}-character "
            "bound (the design point is ~2,300 input tokens per call). Truncating silently would "
            "judge a page the model never saw; narrow the evidence or raise the bound deliberately."
        )
    user = _site_block(site, site_id) + "\n" + _evidence_block(excerpts)
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
) -> list[PreparedCall]:
    """One prepared call per site of the batch, in batch order."""
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    return [
        prepare_call(
            batch_id=batch_id, site=site, store=store, stage=stage, allow_absent=allow_absent
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
    """
    call = prepared.call
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
    # per (site, stage) here, and both refuse to overwrite recorded bytes with different ones.
    stored = answers.write(
        site_id=call.site_id, feature=call.stage.value, body=answer.text.encode("utf-8")
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

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass
class BatchModelReport:
    """One batch's model stage. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    stage: Stage
    site_ids: list[str]
    judgements: list[SiteJudgement]

    @property
    def calls(self) -> int:
        return len(self.judgements)

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
            "totals": {
                "calls": self.calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": self.cost_usd,
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
) -> BatchModelReport:
    """Judge every site of the batch: one call, one ledger line, one stored answer per site.

    Nothing is caught: the first failure propagates, so a batch that could not be measured is
    reported as failed rather than as a smaller batch (`phase3.model.StageResult` has the same
    rule). A re-run re-answers every site and writes a second line per call: the second charge is
    then visible in the ledger instead of hidden behind an invisible retry.
    """
    batch_id = str(batch.get("batch_id") or "")
    if not batch_id:
        raise InputError("batch carries no batch_id")
    prepared = prepare_batch(batch=batch, store=store, stage=stage)
    judgements: list[SiteJudgement] = []
    for item in prepared:
        judged = judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)
        usage = judged.answer.usage
        judgements.append(
            SiteJudgement(
                site_id=item.call.site_id,
                label=item.call.label,
                answer_chars=len(judged.answer.text),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=usage.cost_usd,
                wrote=judged.wrote,
            )
        )
    return BatchModelReport(
        batch_id=batch_id,
        stage=stage,
        site_ids=[item.call.site_id for item in prepared],
        judgements=judgements,
    )

"""The measured cost and time ledger: one append-only line per model call and per fetch.

Why this file exists: the plan carries two cost anchors that cannot both be true — ~40,000
tokens per site (plan §13) and run 1's `3,653,051 tokens / 36 agents x 5 sites` = ~20,295
tokens per site (`output/remediation/phase3_worklist/BATCH_PLAN.md`). They differ by 2x, the
pilot measured neither, and the ratified decision is that the **first instrumented run must
replace both with a measurement** rather than an average.

What is measured here, and what is deliberately not:

* **Measured:** one line per call, carrying the numbers the caller actually received from the
  model API (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`) or
  from the HTTP response (`url`, `http_status`, `bytes`), plus the wall-clock instant. These
  are recorded, never derived.
* **USD, recorded but never computed.** A price table is an assumption, not a measurement (the
  plan's own prices are dated 2026-09-19 assumptions), so this file never applies one to a token
  count. The provider does report a real figure per call - `cost.total` in the `message_end`
  event of the `--mode json` stream, captured in `output/remediation/logs/pi_probe.json` - and
  that reported number is stored verbatim as `cost_usd` on the call's own line (piece 3 added the
  field for exactly that reason: piece 1 had no dollar column because there was no measurement to
  put in one). Totals are then sums of measured figures; nothing is extrapolated.
* **Refused, not defaulted:** a model call without its token counts, or a fetch without the
  outcome actually observed, raises at construction. An unmeasured call cannot be written as
  if it had been measured.

Piece 4 added the fetch line's `outcome` (and `attempt`, `error`, `given_up`) because the first
live batch measured the hole: a `ReadTimeout` on the Overpass target wrote **no line at all**, so
the ledger counted the successes only - exactly the undercount that made one flaky request look
free while it killed the batch. Every attempt now writes a line, a transport failure carries its
reason instead of a status it never saw, and `fetch_failures` totals the attempts that bought
nothing. A fetch line written *before* that field existed (the one line of the pilot's
`LEDGER.jsonl`, 2026-09-21) is counted in `fetches`/`fetch_bytes` and in neither bucket: it is
not guessed at.

Piece 4b added `FetchOutcome.HOST_UNREACHABLE` and the one line shape it carries. A target on a
host that did not answer the run's reachability probe is recorded **once, with `attempt=0`**: no
request left the machine for it, so there is no attempt to number. That is why `attempt` may be 0
here and only here, and why such a line cannot carry `given_up=True` - nothing was asked, so
nothing was given up. The probe itself is an ordinary fetch line (`kind="fetch"`,
`label="host_probe:<host>"`), because it is an ordinary request.

Crash safety: `Ledger.append` opens the file in append mode, writes exactly one line ending in
`\n`, flushes and `os.fsync`s before returning, so a crash loses at most the call in flight and
never leaves a half line behind (a half line would make every later `summarise()` a guess).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from phase3.model import Stage


class LedgerKind(StrEnum):
    MODEL_CALL = "model_call"
    FETCH = "fetch"


class FetchOutcome(StrEnum):
    """How one fetch *attempt* ended. One of these is on every fetch line, so a failure is data.

    Kept in this module rather than in `phase3.fetch_stage` because it is a property of a ledger
    line, and `fetch_stage` imports this module (the other direction would be a cycle).
    """

    #: A 2xx answer arrived and its bytes are on disk. A **valid empty result** (Overpass answers
    #: `"elements": []` with status 200; the pilot's `Petroglyph/overpass.txt`, 287 bytes) is an
    #: `OK` attempt: "I looked and there was nothing" is a result, not a failure.
    OK = "ok"
    #: A response arrived with a non-2xx status. Recorded data, not an exception - the pilot's
    #: 403/404/504/429 were all recorded and its run continued.
    HTTP_ERROR = "http_error"
    #: No response arrived at all (DNS, connect, TLS, reset, read timeout). There is no status to
    #: record, so `http_status` is None and `error` carries the reason instead.
    TRANSPORT_FAILURE = "transport_failure"
    #: The host did not answer this run's reachability probe, so this target was **not attempted**:
    #: no request left the machine for it (`attempt=0` on its line) and `error` carries the probe's
    #: reason. A different fact from `TRANSPORT_FAILURE`, which is a target that *was* asked and got
    #: nothing - "I could not look because the host never answered" versus "I asked and it failed".
    HOST_UNREACHABLE = "host_unreachable"


class LedgerError(ValueError):
    """A ledger line that is not a measurement this module can total."""


def utc_now() -> str:
    """The real clock, at the precision the ledger records (seconds, UTC, ISO 8601)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Entry:
    """One measured call. Exactly one of the two shapes, decided by `kind`."""

    kind: LedgerKind
    stage: Stage
    batch_id: str
    label: str
    at: str | None = None
    #: model-call shape
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    #: The provider's own reported cost (`cost.total`) of this call, in USD. Recorded as
    #: reported; never computed from a price table (see the module docstring).
    cost_usd: float | None = None
    #: fetch shape
    url: str | None = None
    http_status: int | None = None
    bytes: int | None = None
    #: fetch shape, piece 4: how the attempt ended, which attempt it was (1-based), the reason a
    #: transport failure had none of its own, and whether this attempt was the last one for that
    #: target (so the target ends with no evidence). `given_up` cannot be inferred from a single
    #: line: only the writer knows that no further attempt follows.
    outcome: FetchOutcome | None = None
    attempt: int | None = None
    error: str | None = None
    given_up: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _coerce(LedgerKind, self.kind, "kind"))
        object.__setattr__(self, "stage", _coerce(Stage, self.stage, "stage"))
        if not self.batch_id:
            raise LedgerError("a ledger entry needs the batch_id it belongs to")
        if not self.label:
            raise LedgerError("a ledger entry needs a label")

        if self.kind is LedgerKind.MODEL_CALL:
            if not self.model:
                raise LedgerError(f"{self.label}: a model call needs the model it called")
            for name in ("input_tokens", "output_tokens"):
                value = getattr(self, name)
                if value is None:
                    raise LedgerError(
                        f"{self.label}: {name} missing - token counts are recorded per call "
                        "and never estimated"
                    )
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise LedgerError(f"{self.label}: {name}={value!r} is not a token count")
            for name in ("cache_read_tokens", "cache_write_tokens"):
                value = getattr(self, name)
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool) or value < 0
                ):
                    raise LedgerError(f"{self.label}: {name}={value!r} is not a token count")
            if self.cost_usd is not None and (
                not isinstance(self.cost_usd, (int, float))
                or isinstance(self.cost_usd, bool)
                or self.cost_usd != self.cost_usd
                or self.cost_usd in (float("inf"), float("-inf"))
                or self.cost_usd < 0
            ):
                raise LedgerError(f"{self.label}: cost_usd={self.cost_usd!r} is not a cost")
            for name in ("url", "http_status", "bytes", "attempt", "error", "given_up"):
                if getattr(self, name) is not None:
                    raise LedgerError(f"{self.label}: a model call cannot carry {name}")
            if self.outcome is not None:
                raise LedgerError(f"{self.label}: a model call cannot carry outcome")
        else:
            if not self.url:
                raise LedgerError(f"{self.label}: a fetch needs the url it fetched")
            self._check_fetch_attempt()
            for name in ("model", "input_tokens", "output_tokens", "cost_usd"):
                if getattr(self, name) is not None:
                    raise LedgerError(f"{self.label}: a fetch cannot carry {name}")

    def _check_fetch_attempt(self) -> None:
        """The fetch line's shape: an observed outcome, and a status exactly when one arrived."""
        if self.outcome is None:
            raise LedgerError(
                f"{self.label}: a fetch records the outcome observed (one of "
                f"{[m.value for m in FetchOutcome]}); a request that bought nothing is written "
                "as data too, never left out"
            )
        object.__setattr__(self, "outcome", _coerce(FetchOutcome, self.outcome, "outcome"))
        answered = self.outcome in (FetchOutcome.OK, FetchOutcome.HTTP_ERROR)
        if answered:
            if not isinstance(self.http_status, int) or not 100 <= self.http_status <= 599:
                raise LedgerError(
                    f"{self.label}: outcome={self.outcome} needs the status observed, got "
                    f"http_status={self.http_status!r}"
                )
            if self.outcome is FetchOutcome.OK and not 200 <= self.http_status < 300:
                raise LedgerError(
                    f"{self.label}: outcome=ok with http_status={self.http_status} - a 2xx answer "
                    "is the only outcome that buys a page"
                )
            if self.outcome is FetchOutcome.HTTP_ERROR and 200 <= self.http_status < 300:
                raise LedgerError(
                    f"{self.label}: outcome=http_error with the 2xx status "
                    f"{self.http_status} - the outcome and the status disagree"
                )
            if self.error is not None:
                raise LedgerError(
                    f"{self.label}: a response that arrived is recorded by its status, not by "
                    f"an error string ({self.error!r})"
                )
        else:
            if self.http_status is not None:
                raise LedgerError(
                    f"{self.label}: outcome={self.outcome.value} arrived with no response, so it "
                    f"cannot carry http_status={self.http_status!r}"
                )
            if not self.error:
                raise LedgerError(
                    f"{self.label}: outcome={self.outcome.value} needs the reason (DNS, connect, "
                    "reset, timeout, or the host probe that never answered) - a failure with no "
                    "reason is not a measurement"
                )
        if self.outcome is FetchOutcome.HOST_UNREACHABLE:
            # No request was made for this target, so there is no attempt to number: `attempt=0` is
            # that fact, and every other outcome needs a 1-based attempt number.
            if (
                not isinstance(self.attempt, int)
                or isinstance(self.attempt, bool)
                or self.attempt != 0
            ):
                raise LedgerError(
                    f"{self.label}: outcome=host_unreachable means no request was made, so "
                    f"attempt must be 0, got {self.attempt!r}"
                )
        elif (
            not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1
        ):
            raise LedgerError(
                f"{self.label}: attempt={self.attempt!r} is not a 1-based attempt number; a retry "
                "is countable only because every attempt has its own line"
            )
        if not isinstance(self.given_up, bool):
            raise LedgerError(
                f"{self.label}: given_up={self.given_up!r} is not a boolean; every fetch line says "
                "whether it was the target's last attempt"
            )
        if self.outcome is FetchOutcome.HOST_UNREACHABLE and self.given_up:
            raise LedgerError(
                f"{self.label}: outcome=host_unreachable cannot carry given_up=True; nothing was "
                "given up on a target that was never asked"
            )
        if self.bytes is None or not isinstance(self.bytes, int) or self.bytes < 0:
            raise LedgerError(f"{self.label}: bytes={self.bytes!r} is not a byte count")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["stage"] = self.stage.value
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _coerce(enum_cls: type[StrEnum], value: Any, what: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise LedgerError(f"{what}: {value!r} is not one of {[m.value for m in enum_cls]}") from exc


@dataclass
class Ledger:
    """Append-only writer. Kept a thin wrapper so the clock is injectable in tests."""

    path: Path
    clock: Callable[[], str] = utc_now

    def append(self, entry: Entry) -> Entry:
        """Write `entry` as one line and return it with the recorded timestamp."""
        if entry.at is None:
            entry = _with_time(entry, self.clock())
        line = entry.to_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry


def _with_time(entry: Entry, at: str) -> Entry:
    return Entry(
        kind=entry.kind,
        stage=entry.stage,
        batch_id=entry.batch_id,
        label=entry.label,
        at=at,
        model=entry.model,
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        cache_read_tokens=entry.cache_read_tokens,
        cache_write_tokens=entry.cache_write_tokens,
        cost_usd=entry.cost_usd,
        url=entry.url,
        http_status=entry.http_status,
        bytes=entry.bytes,
        outcome=entry.outcome,
        attempt=entry.attempt,
        error=entry.error,
        given_up=entry.given_up,
    )


@dataclass(frozen=True)
class StageTotals:
    """Everything the ledger measured for one stage. All sums, nothing derived."""

    stage: str
    model_calls: int = 0
    fetches: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: Sum of the per-call costs the provider reported. A sum of measurements, not a price applied
    #: to a token count.
    cost_usd: float = 0.0
    fetch_bytes: int = 0
    #: Lines whose recorded outcome bought nothing (`http_error`, `transport_failure`, and
    #: `host_unreachable` - a target that was never asked because its host did not answer the run's
    #: probe, which counts here exactly like a transport failure). `fetches` counts **lines**: every
    #: request has one, and a not-attempted target has a line without a request. So a target retried
    #: twice appears twice, and `fetch_failures` answers exactly what the pilot's count asked: how
    #: much of this batch's traffic bought nothing.
    fetch_failures: int = 0
    first_at: str | None = None
    last_at: str | None = None

    @property
    def total_tokens(self) -> int:
        """Input + output as recorded. Cache reads are reported separately, not added in."""
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_tokens"] = self.total_tokens
        return payload


@dataclass(frozen=True)
class LedgerSummary:
    """The whole ledger, totalled by stage, in a fixed stage order."""

    by_stage: dict[str, StageTotals] = field(default_factory=dict)
    lines: int = 0

    @property
    def total(self) -> StageTotals:
        return _totals(
            stage="all",
            entries=list(self.by_stage.values()),
        )


def read_entries(path: Path) -> list[dict[str, Any]]:
    """Every line of the ledger, parsed. A missing file or a broken line raises."""
    if not path.exists():
        raise FileNotFoundError(f"no ledger at {path}: nothing has been measured yet")
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            if not raw.endswith("\n"):
                raise LedgerError(f"{path}:{lineno}: line does not end in a newline (truncated?)")
            text = raw.strip()
            if not text:
                raise LedgerError(f"{path}:{lineno}: empty line")
            try:
                entries.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise LedgerError(f"{path}:{lineno}: not JSON: {exc}") from exc
    return entries


def summarise(path: Path) -> LedgerSummary:
    """Total the ledger by stage. Every figure is a sum over recorded lines."""
    entries = read_entries(path)
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if "stage" not in entry or "kind" not in entry:
            raise LedgerError(f"{path}: a ledger line carries no stage/kind: {entry!r}")
        by_stage.setdefault(str(entry["stage"]), []).append(entry)
    return LedgerSummary(
        by_stage={stage: _totals(stage=stage, entries=rows) for stage, rows in by_stage.items()},
        lines=len(entries),
    )


def _totals(stage: str, entries: Iterable[Any]) -> StageTotals:
    calls = fetches = failures = 0
    tokens = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    cost_usd = 0.0
    fetch_bytes = 0
    times: list[str] = []
    for entry in entries:
        if isinstance(entry, StageTotals):
            calls += entry.model_calls
            fetches += entry.fetches
            tokens["input_tokens"] += entry.input_tokens
            tokens["output_tokens"] += entry.output_tokens
            tokens["cache_read_tokens"] += entry.cache_read_tokens
            tokens["cache_write_tokens"] += entry.cache_write_tokens
            cost_usd += entry.cost_usd
            fetch_bytes += entry.fetch_bytes
            failures += entry.fetch_failures
            times.extend(t for t in (entry.first_at, entry.last_at) if t)
            continue
        if entry["kind"] == LedgerKind.MODEL_CALL.value:
            calls += 1
            for name in tokens:
                tokens[name] += int(entry.get(name) or 0)
            cost_usd += float(entry.get("cost_usd") or 0.0)
        else:
            fetches += 1
            fetch_bytes += int(entry.get("bytes") or 0)
            # A line without an `outcome` predates piece 4; it is not counted as a failure (that
            # would invent one) and not as a success either. See the module docstring.
            if entry.get("outcome") not in (None, FetchOutcome.OK.value):
                failures += 1
        if entry.get("at"):
            times.append(str(entry["at"]))
    times.sort()
    return StageTotals(
        stage=stage,
        model_calls=calls,
        fetches=fetches,
        fetch_bytes=fetch_bytes,
        fetch_failures=failures,
        cost_usd=cost_usd,
        first_at=times[0] if times else None,
        last_at=times[-1] if times else None,
        **tokens,
    )

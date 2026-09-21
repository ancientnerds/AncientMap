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
  status actually observed, raises at construction. An unmeasured call cannot be written as
  if it had been measured.

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
            for name in ("url", "http_status", "bytes"):
                if getattr(self, name) is not None:
                    raise LedgerError(f"{self.label}: a model call cannot carry {name}")
        else:
            if not self.url:
                raise LedgerError(f"{self.label}: a fetch needs the url it fetched")
            if self.http_status is None:
                raise LedgerError(
                    f"{self.label}: a fetch records the status observed; a network failure "
                    "raises in the fetcher and is never written as an empty result"
                )
            if not isinstance(self.http_status, int) or not 100 <= self.http_status <= 599:
                raise LedgerError(f"{self.label}: http_status={self.http_status!r} is not a status")
            if self.bytes is None or not isinstance(self.bytes, int) or self.bytes < 0:
                raise LedgerError(f"{self.label}: bytes={self.bytes!r} is not a byte count")
            for name in ("model", "input_tokens", "output_tokens", "cost_usd"):
                if getattr(self, name) is not None:
                    raise LedgerError(f"{self.label}: a fetch cannot carry {name}")

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
    calls = fetches = 0
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
        if entry.get("at"):
            times.append(str(entry["at"]))
    times.sort()
    return StageTotals(
        stage=stage,
        model_calls=calls,
        fetches=fetches,
        fetch_bytes=fetch_bytes,
        cost_usd=cost_usd,
        first_at=times[0] if times else None,
        last_at=times[-1] if times else None,
        **tokens,
    )

"""Pipelined site-short production: the globe recorder is the only serial stage.

Measured per site (17.09.): preparation (export, images, VLM selection, voice)
~2 min, recording ~12 min, render + audit ~1 min. Run one after another that is
15 min per site while the recorder — the expensive resource — idles a fifth of
the time.

Here the three stages overlap:

    prepare (threads, network/API bound)  ─┐
                                           ├─► record (ONE browser, serial)
                                           └─► render + audit (threads, CPU)

The recorder takes every site that is ready as one `--batch` session, so Vite
and Chrome start once per session instead of once per site (~1 min each).
A site that fails a stage drops out; the others keep going.

`plan_sessions`, `next_batch` and `stage_steps` are pure and unit tested; the
rest is subprocess plumbing.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PREP_STEPS = "export,images,select,tts"
RENDER_STEPS = "render"
PREP_WORKERS = 3  # Commons downloads and MiniMax calls, not CPU
RENDER_WORKERS = 2  # ffmpeg; more would starve the recorder's browser
RECORD_MAX_SESSION = 8  # sites per browser session; a crash costs at most this many
RECORD_GATHER_S = 20.0  # wait this long for more prepared sites before starting a session

_TIMEOUT = object()  # queue.get timed out: record what is already pending


@dataclass
class SiteJob:
    name: str
    site_dir: Path | None = None
    failed_stage: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed_stage is None


def stage_steps() -> tuple[str, str]:
    """The two subprocess step lists: everything before the recorder, and after."""
    return PREP_STEPS, RENDER_STEPS


def plan_sessions(ready: list[str], max_per_session: int = RECORD_MAX_SESSION) -> list[list[str]]:
    """Split sites that are ready to record into browser sessions."""
    return [ready[i : i + max_per_session] for i in range(0, len(ready), max_per_session)]


def next_batch(
    pending: list[str], max_per_session: int = RECORD_MAX_SESSION
) -> tuple[list[str], list[str]]:
    """(sites for the next session, what stays pending)."""
    return pending[:max_per_session], pending[max_per_session:]


def _run_module(args: list[str], log: Path) -> bool:
    """Run `python -m pipeline.video …` as its own process: a long-lived process
    would keep the code it imported at start, and one crash would take the whole
    run with it."""
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {time.strftime('%H:%M:%S')} {' '.join(args)}\n")
        fh.flush()
        proc = subprocess.run(
            [sys.executable, "-m", "pipeline.video", *args], stdout=fh, stderr=subprocess.STDOUT
        )
    return proc.returncode == 0


def _step(name: str, steps: str, log: Path) -> bool:
    ok = _run_module(["short", "--name", name, "--steps", steps], log)
    logger.info("%-22s %-28s %s", steps, name[:28], "ok" if ok else "FAILED")
    return ok


def record_session(
    targets: list[tuple[Path, Path]], log: Path, recorder_dir: Path, api_target: str
) -> bool:
    """One browser session for several sites: a manifest of {input, out} pairs
    goes to the recorder, which keeps Vite and Chrome up across all of them."""
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH; the recorder needs Node")
    manifest = log.parent / "record-batch.json"
    manifest.write_text(
        json.dumps([{"input": i.as_posix(), "out": o.as_posix()} for i, o in targets], indent=1),
        encoding="utf-8",
    )
    cmd = [
        npm, "run", "video:record", "--",
        "short-opening,short-return",
        "--portrait", "--fps", "60",
        "--batch", manifest.as_posix(),
    ]  # fmt: skip
    env = {**os.environ, "VITE_DEV_API_TARGET": api_target}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {time.strftime('%H:%M:%S')} record session: {len(targets)} site(s)\n")
        fh.flush()
        proc = subprocess.run(cmd, cwd=recorder_dir, env=env, stdout=fh, stderr=subprocess.STDOUT)
    logger.info("record session of %d site(s): rc=%s", len(targets), proc.returncode)
    return proc.returncode == 0


def run_pipeline(
    names: list[str],
    log: Path,
    recorder_dir: Path,
    api_target: str,
    site_dir_for,
    *,
    prep_workers: int = PREP_WORKERS,
    render_workers: int = RENDER_WORKERS,
) -> dict[str, SiteJob]:
    """Prepare, record and render `names` with the three stages overlapping.
    `site_dir_for(name)` gives the site's asset directory. One SiteJob per name."""
    jobs = {name: SiteJob(name) for name in names}
    prep_q: queue.Queue = queue.Queue()
    rec_q: queue.Queue = queue.Queue()
    ren_q: queue.Queue = queue.Queue()
    for name in names:
        prep_q.put(name)

    def prep_worker() -> None:
        while (name := prep_q.get()) is not None:
            if _step(name, PREP_STEPS, log):
                jobs[name].site_dir = site_dir_for(name)
                rec_q.put(name)
            else:
                jobs[name].failed_stage = "prepare"

    def record_worker() -> None:
        pending: list[str] = []
        producers_done = False
        while not producers_done or pending:
            if not producers_done:
                try:
                    item = rec_q.get(timeout=RECORD_GATHER_S) if pending else rec_q.get()
                except queue.Empty:
                    item = _TIMEOUT
                if item is None:
                    producers_done = True
                elif item is not _TIMEOUT:
                    pending.append(item)
                    if len(pending) < RECORD_MAX_SESSION:
                        continue
            if not pending:
                continue
            batch, pending = next_batch(pending)
            targets = [(jobs[n].site_dir / "site.json", jobs[n].site_dir / "clips") for n in batch]
            ok = record_session(targets, log, recorder_dir, api_target)
            for name in batch:
                clips = jobs[name].site_dir / "clips"
                if (clips / "short-opening.mp4").exists() and (clips / "short-return.mp4").exists():
                    ren_q.put(name)
                else:
                    jobs[name].failed_stage = "record"
                    if not ok:
                        jobs[name].notes.append("recorder session reported an error")
        for _ in range(render_workers):
            ren_q.put(None)

    def render_worker() -> None:
        while (name := ren_q.get()) is not None:
            if not _step(name, RENDER_STEPS, log):
                jobs[name].failed_stage = "render"
            elif not _run_module(["audit", "--name", name], log):
                jobs[name].failed_stage = "audit"

    preps = [threading.Thread(target=prep_worker, daemon=True) for _ in range(prep_workers)]
    recorder = threading.Thread(target=record_worker, daemon=True)
    renderers = [threading.Thread(target=render_worker, daemon=True) for _ in range(render_workers)]
    for thread in (*preps, recorder, *renderers):
        thread.start()
    for _ in preps:
        prep_q.put(None)
    for thread in preps:
        thread.join()
    rec_q.put(None)
    recorder.join()
    for thread in renderers:
        thread.join()
    for job in jobs.values():
        if not job.ok:
            logger.warning("%s failed at %s %s", job.name, job.failed_stage, "; ".join(job.notes))
    logger.info("pipeline done: %d/%d ok", sum(j.ok for j in jobs.values()), len(jobs))
    return jobs

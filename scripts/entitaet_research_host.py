"""Run Theo deep-research on the HOST (no api container) for the ENTITÄT book.

Bypasses the Docker api image (build is flaky) — runs the ConvergenceOrchestrator
directly via the host .venv, talking to the running db/redis/qdrant containers on
localhost (the .env already uses localhost hosts). Reports are written straight
into the FantasyAdventure book workspace.

Usage (from AncientMap repo root):
  ./.venv/Scripts/python.exe scripts/entitaet_research_host.py --only polygonal-masonry --fast
  ./.venv/Scripts/python.exe scripts/entitaet_research_host.py --priority P1
  ./.venv/Scripts/python.exe scripts/entitaet_research_host.py            # all, full depth, resume

Resume-safe: skips slugs whose <slug>.md already exists in the out dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# --- Load env from AncientMap's .env / .env.local BEFORE importing the app ---
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))  # so `pipeline` imports when run as a script


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        for fn in (".env", ".env.local"):
            p = _REPO / fn
            if p.exists():
                load_dotenv(p, override=False)
        return
    except Exception:
        pass
    # Manual fallback parser
    for fn in (".env", ".env.local"):
        p = _REPO / fn
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_env()

OUT_DIR = Path(
    os.getenv(
        "ENTITAET_OUT",
        r"C:\PythonProjects\FantasyAdventure\docs\entitaet\research\reports",
    )
)

# slug -> (priority, question)
QUESTIONS: dict[str, tuple[str, str]] = {
    "polygonal-masonry": (
        "P1",
        "What explains the extreme precision of polygonal megalithic masonry at sites like Sacsayhuamán, Cusco, Egyptian granite work, and Puma Punku? Compare mainstream construction theories with documented anomalies and alternative hypotheses, with evidence on each side.",
    ),
    "deluge-younger-dryas": (
        "P1",
        "How widespread are global flood/deluge myths across cultures, and what is the current scientific evidence for and against the Younger Dryas impact hypothesis as a real cataclysm around 12,900 years ago?",
    ),
    "plasma-sky-rockart": (
        "P1",
        "What is Anthony Peratt's plasma-instability ('squatter man') hypothesis for the similarity of worldwide petroglyphs, and how do auroral and plasma phenomena appear in ancient myth and rock art across cultures?",
    ),
    "anunnaki-nibiru": (
        "P1",
        "What do Sumerian and Mesopotamian texts (Enuma Elish, the Tiamat 'celestial battle') actually say about the gods and a destroyed planet, and how do Zecharia Sitchin's Anunnaki/Nibiru claims compare with mainstream Assyriology?",
    ),
    "mars-catastrophism": (
        "P1",
        "What is the mainstream evidence and the fringe 'cosmic catastrophe' claims about Mars losing its atmosphere and large-scale surface scarring (Valles Marineris, electric-universe claims) — contrast the science with the catastrophist narratives?",
    ),
    "cyclical-world-ages": (
        "P1",
        "How do cyclical 'world ages' and recurring world-destructions appear across mythologies — the Aztec Five Suns, Hindu yugas, Hesiod's ages of man, the Maya long count, and Jewish/Kabbalistic world-cycles? What patterns recur?",
    ),
    "kybalion-hermetica": (
        "P2",
        "What are the seven Hermetic principles of the Kybalion, what is their true historical provenance (the 1908 'Three Initiates' text vs ancient Hermeticism), and how do they relate to the Corpus Hermeticum and 'as above, so below'?",
    ),
    "bosnian-pyramids": (
        "P2",
        "What are the claims and the scientific assessment of the Bosnian Pyramids near Visoko and the Ravne tunnel complex — the geology, the dating, the 'energy/ultrasound' claims, and the academic dispute around Semir Osmanagić?",
    ),
    "pineal-dmt-thirdeye": (
        "P2",
        "What is the scientific status of endogenous DMT and the pineal gland in altered states (Rick Strassmann's work, near-death and out-of-body parallels), and how does 'third eye' pineal symbolism appear across Egyptian and Hindu traditions?",
    ),
    "remote-viewing-stargate": (
        "P2",
        "What did the declassified Stargate Project and the SRI remote-viewing program actually find, who was Ingo Swann, and what is the documented evidence for and against remote viewing?",
    ),
    "cargo-cult-contact": (
        "P3",
        "What do cargo cults (John Frum, Melanesia) and uncontacted-peoples first-contact dynamics (North Sentinel Island) reveal about how humans deify or demonize technologically superior visitors?",
    ),
    "paleocontact-iconography": (
        "P3",
        "What specific artifacts and iconography are cited in ancient-astronaut/paleocontact claims, and how does mainstream scholarship explain the recurring global 'gods came from the sky' motif?",
    ),
}


def _maybe_shrink_config() -> None:
    """THEO_FAST=1 → fewer angles/rounds so a run finishes in ~15-20 min."""
    if os.getenv("THEO_FAST") != "1":
        return
    import pipeline.lyra.convergence_orchestrator as co

    _orig = co.ResearchConfig

    def _small():
        c = _orig()
        c.max_angles = 5
        c.initial_specialist_count = 3
        c.min_specialists = 2
        c.max_specialists = 5
        c.max_search_rounds_per_angle = 3
        c.max_debate_rounds = 1
        return c

    co.ResearchConfig = _small


async def _run_one(slug: str, question: str) -> dict:
    from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

    t0 = time.monotonic()
    counter = {"n": 0}

    def emit(event: dict) -> None:
        counter["n"] += 1
        if counter["n"] % 25 == 0:
            mins = (time.monotonic() - t0) / 60.0
            print(
                f"  [{slug}] {counter['n']} events, {mins:.1f}min, last={event.get('type')}",
                flush=True,
            )

    print(f"[theo] START {slug}: {question[:80]}...", flush=True)
    ctx = await ConvergenceOrchestrator().run(question, emit, request_id="")
    dur = round((time.monotonic() - t0) / 60.0, 1)

    if ctx.error:
        print(f"[theo] FAILED {slug}: {ctx.error}", flush=True)
        return {"slug": slug, "error": str(ctx.error), "duration_min": dur}

    qs = ctx.quality_score or {}
    paper = ctx.paper_text or ""
    title = ctx.paper_title or slug
    sources = []
    try:
        sources = [getattr(s, "url", None) or getattr(s, "title", "") for s in ctx.registry.sources]
    except Exception:
        pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slug}.md").write_text(f"# {title}\n\n{paper}", encoding="utf-8")
    meta = {
        "slug": slug,
        "title": title,
        "question": question,
        "duration_min": dur,
        "quality_score": qs.get("score"),
        "badge": qs.get("badge"),
        "dimensions": qs.get("dimensions", {}),
        "citation_sources": len(sources),
        "sources": sources[:200],
        "specialists": len(getattr(ctx, "specialist_analyses", {}) or {}),
        "paper_chars": len(paper),
        "llm_calls": getattr(ctx, "llm_call_count", None),
        "total_tokens": getattr(ctx, "total_tokens", None),
    }
    (OUT_DIR / f"{slug}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(
        f"[theo] DONE {slug}: {dur}min, q={qs.get('score')} {qs.get('badge')}, {len(sources)} sources, {len(paper)} chars",
        flush=True,
    )
    return meta


async def _main(slugs: list[str], concurrency: int) -> None:
    todo = [s for s in slugs if not (OUT_DIR / f"{s}.md").exists()]
    skipped = [s for s in slugs if s not in todo]
    if skipped:
        print(f"[theo] resume: skipping already-done {skipped}", flush=True)
    print(f"[theo] running {len(todo)} question(s), concurrency={concurrency}: {todo}", flush=True)

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(slug):
        async with sem:
            try:
                return await _run_one(slug, QUESTIONS[slug][1])
            except Exception as exc:  # noqa: BLE001
                print(f"[theo] EXC {slug}: {exc!r}", flush=True)
                return {"slug": slug, "error": repr(exc)}

    results = await asyncio.gather(*[_guarded(s) for s in todo])
    summary = OUT_DIR / "_batch_summary.json"
    prev = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else []
    prev.extend(results)
    summary.write_text(
        json.dumps(prev, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    ok = sum(1 for r in results if r and not r.get("error"))
    print(f"\n[theo] BATCH COMPLETE: {ok}/{len(todo)} succeeded. Reports in {OUT_DIR}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated slugs")
    ap.add_argument("--priority", default="", help="P1 | P2 | P3")
    ap.add_argument(
        "--fast", action="store_true", help="THEO_FAST shallow profile (~15-20 min/run)"
    )
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()

    if args.fast:
        os.environ["THEO_FAST"] = "1"
    _maybe_shrink_config()

    if args.only:
        slugs = [s.strip() for s in args.only.split(",") if s.strip() in QUESTIONS]
    elif args.priority:
        slugs = [s for s, (p, _) in QUESTIONS.items() if p == args.priority.upper()]
    else:
        # default order: P1, P2, P3
        order = {"P1": 0, "P2": 1, "P3": 2}
        slugs = sorted(QUESTIONS, key=lambda s: order.get(QUESTIONS[s][0], 9))

    asyncio.run(_main(slugs, args.concurrency))


if __name__ == "__main__":
    main()

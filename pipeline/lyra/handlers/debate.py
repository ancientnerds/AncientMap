"""Convergence-based debate — runs until no new challenges."""

import asyncio
import json
import logging
from pathlib import Path

from pipeline.lyra.config import _get_settings
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.research_events import DebateComplete, SynthesisReady
from pipeline.lyra.research_state import ResearchPhase
from pipeline.lyra.schemas import DEBATE_CHALLENGE_SCHEMA, DEBATE_DEFENSE_SCHEMA
from pipeline.lyra.theo_specialists import _SPECIALIST_BY_ID

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class DebateHandler(BaseHandler):
    def register(self):
        self.bus.on(SynthesisReady, self._on_synthesis_ready)

    async def _on_synthesis_ready(self, event: SynthesisReady):
        self.state.phase = ResearchPhase.DEBATING
        max_rounds = self.state.config.max_debate_rounds

        if max_rounds <= 0:
            self.state.log("debate", "Debate skipped (max_debate_rounds=0)")
            await self.bus.emit(DebateComplete())
            return

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "debate",
                "status": "start",
                "meta": {"subtask_total": max_rounds},
            }
        )

        challenge_prompt = (PROMPTS_DIR / "theo_debate_challenge.txt").read_text(encoding="utf-8")
        defense_prompt = (PROMPTS_DIR / "theo_debate_defense.txt").read_text(encoding="utf-8")
        synthesis_json = json.dumps(self.state.synthesis, indent=2)

        all_challenges: list[dict] = []
        all_defenses: list[dict] = []

        # Get specialist objects for active panel members
        active_specs = []
        for ap in self.state.active_specialists:
            spec = _SPECIALIST_BY_ID.get(ap.specialist_id)
            if spec:
                active_specs.append(spec)

        # Build per-specialist findings lookup from all angles
        spec_findings: dict[str, list[dict]] = {}
        for angle in self.state.angles:
            for f in angle.findings:
                sid = f.get("specialist_id")
                if sid:
                    spec_findings.setdefault(sid, []).append(f)

        rnd = 0
        for rnd in range(1, max_rounds + 1):
            self.emit_sse(
                {
                    "type": "status",
                    "content": f"Debate round {rnd}/{max_rounds}...",
                    "subtask_done": rnd - 1,
                    "subtask_total": max_rounds,
                }
            )

            # Challenge phase
            round_challenges: list[dict] = []
            for spec in active_specs:
                system_msg = f"You are {spec.name}, {spec.title}.\n\n{spec.perspective}\n\n{challenge_prompt}"
                user_msg = (
                    f"## Synthesis to challenge\n\n{synthesis_json}\n\n"
                    f"## Your original findings\n\n{json.dumps(spec_findings.get(spec.id, []), indent=2)}"
                )

                settings = _get_settings()
                async with self.semaphore:
                    parsed = await asyncio.to_thread(
                        structured_llm_call,
                        system_msg,
                        user_msg,
                        DEBATE_CHALLENGE_SCHEMA,
                        self.state.config.max_tokens_per_call,
                        settings,
                        temperature=settings.temperature_verification,
                    )
                self.state.llm_call_count += 1
                challenges = parsed.get("strengthening_suggestions", parsed.get("challenges", []))
                for c in challenges:
                    c["challenger_id"] = spec.id
                round_challenges.extend(challenges)

            all_challenges.extend(round_challenges)

            if not round_challenges:
                self.emit_sse(
                    {"type": "status", "content": f"Round {rnd}: no challenges — debate converged"}
                )
                self.state.log("debate", f"Debate converged at round {rnd} (no challenges)")
                break

            # Defense phase
            for spec in active_specs:
                my_challenges = [
                    c for c in round_challenges if c.get("target_specialist") == spec.id
                ]
                if not my_challenges:
                    continue

                system_msg = (
                    f"You are {spec.name}, {spec.title}.\n\n{spec.perspective}\n\n{defense_prompt}"
                )
                user_msg = (
                    f"## Challenges directed at you\n\n{json.dumps(my_challenges, indent=2)}\n\n"
                    f"## Your original findings\n\n{json.dumps(spec_findings.get(spec.id, []), indent=2)}"
                )

                settings = _get_settings()
                async with self.semaphore:
                    parsed = await asyncio.to_thread(
                        structured_llm_call,
                        system_msg,
                        user_msg,
                        DEBATE_DEFENSE_SCHEMA,
                        self.state.config.max_tokens_per_call,
                        settings,
                        temperature=settings.temperature_verification,
                    )
                self.state.llm_call_count += 1
                defenses = parsed.get("incorporations", parsed.get("defenses", []))
                for d in defenses:
                    d["defender_id"] = spec.id
                all_defenses.extend(defenses)

            self.state.log(
                "debate", f"Round {rnd}: {len(round_challenges)} challenges, defenses collected"
            )

        self.state.debate_result = {
            "rounds": rnd,
            "challenges": all_challenges,
            "defenses": all_defenses,
        }

        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "debate",
                "status": "done",
                "meta": {
                    "rounds": rnd,
                    "challenges": len(all_challenges),
                    "defenses": len(all_defenses),
                },
            }
        )

        await self.bus.emit(DebateComplete())

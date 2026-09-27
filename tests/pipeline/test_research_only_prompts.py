"""The M3 writing prompts and the LLM calls that read them are gone (research-only split)."""

from pathlib import Path

from pipeline.lyra import coherence_pass, hallucination_gate

PROMPTS = Path(__file__).resolve().parents[2] / "pipeline" / "lyra" / "prompts"
GONE = (
    "v2_paper_outline.txt",
    "v2_paper_hook.txt",
    "v2_paper_section.txt",
    "v2_paper_connecting.txt",
    "v2_paper_otherside.txt",
    "v2_paper_assessment.txt",
    "coherence_pass.txt",
    "hallucination_repair.txt",
)


def test_writing_prompts_are_deleted():
    assert [name for name in GONE if (PROMPTS / name).exists()] == []


def test_only_the_deterministic_checks_remain():
    assert not hasattr(coherence_pass, "run_coherence_pass")
    assert not hasattr(hallucination_gate, "repair_prose")
    for name in ("extract_title_terms", "check_title_terms_in_body", "extract_numeric_claims"):
        assert callable(getattr(coherence_pass, name))
    for name in ("extract_specifics", "verify_against_pack", "delete_sentences_with_specifics"):
        assert callable(getattr(hallucination_gate, name))

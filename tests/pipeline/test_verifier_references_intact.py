"""Regression: verify_all_citations must NEVER touch the References list.

Run #12 reproducer — when the verifier rejected citations [5]..[9] from
the prose, the blanket `re.sub(r"\\s*\\[5\\]", "", text)` also stripped
the leading `[5]` of the corresponding *reference-list entry*, gluing
the rest of that entry's title + URL onto the previous entry's line.
End result: 5 of 47 references kept their `[N]` marker; the other 42
became orphan text appended to the survivors, and the frontend
parseReferenceCitations regex (`^\\[(\\d+)\\]…`) only saw 5 of them.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from pipeline.lyra import citation_verifier


def _run_verify(text: str, sources: list[dict], rejected: set[int]) -> str:
    """Stub out the LLM call so verify_one_citation answers per
    `rejected` set without touching any network."""

    async def fake_verify_one(
        sentence: str,
        cite_num: int,
        source_title: str,
        source_snippet: str,
        source_url: str,
        settings,
        state=None,
    ):
        return (cite_num not in rejected, "stub")

    with patch.object(citation_verifier, "_verify_one_citation", new=fake_verify_one):
        return asyncio.run(
            citation_verifier.verify_all_citations(
                text=text,
                sources=sources,
                settings=None,
                max_iterations=1,
            )
        )


def test_rejecting_a_citation_does_not_glue_reference_entries() -> None:
    paper = (
        "Some prose with a fact [4] and another fact [5] and a third [6].\n"
        "\n"
        "## References\n"
        "\n"
        "[4] Drought caused the downfall — https://example.com/d (accessed 2026-05-12)\n"
        "[5] Who Were the Enigmatic Sea Peoples — https://example.com/w (accessed 2026-05-12)\n"
        "[6] Ancient DNA sheds light — https://example.com/a (accessed 2026-05-12)\n"
    )
    sources = [
        {"citation": 4, "label": "Drought", "snippet": "x", "url": "https://example.com/d"},
        {"citation": 5, "label": "Who", "snippet": "x", "url": "https://example.com/w"},
        {"citation": 6, "label": "Ancient DNA", "snippet": "x", "url": "https://example.com/a"},
    ]
    out = _run_verify(paper, sources, rejected={5})

    # The references list MUST still start each surviving entry with `[N]`
    # on its own line. The old bug stripped `[5]` from the line and turned
    # `\n[5] Who Were ...` into ` Who Were ...`, gluing that text onto the
    # end of `[4] Drought...`.
    refs = out.split("## References", 1)[1]
    lines = [line for line in refs.splitlines() if line.strip()]
    # Allow for the prune step to drop the orphaned [5] entry entirely —
    # what we forbid is leaving its title/URL stuck onto another entry.
    assert "[4] Drought" in refs
    assert "[6] Ancient DNA" in refs
    # The 'Who Were the Enigmatic' title must NOT survive as orphan text
    # attached to a different reference's line. It can stay as its own
    # `[5] Who Were ...` line (verifier doesn't prune orphaned references —
    # that's a separate stage) OR get cleanly removed in a later pass.
    refs_4_line = next(line for line in lines if line.startswith("[4]"))
    refs_6_line = next(line for line in lines if line.startswith("[6]"))
    assert "Who Were" not in refs_4_line
    assert "Who Were" not in refs_6_line

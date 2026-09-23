"""Phases 4 and 5: descriptions and card texts assembled by code from pinned Wikipedia revisions.

The design is entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` ("Phases 4
and 5, final design"): the model picks sentence and span ids, code assembles every byte, and a
verifier that never imports the assembler re-derives them. `model4` holds the records every stage
reads and writes; `docs/procedures/PHASE4_CONTRACTS.md` names which track owns which module.

Import shim. The package is not installed, so it is imported the way `phase3` is: with
`scripts/remediation` on `sys.path` (the tests insert it; a module run as a script inserts it with
the same two lines every `phase3` module carries, `if __package__ in (None, ""):
sys.path.insert(0, <scripts/remediation>)`). What `phase3` leaves to one module
(`phase3/search_evidence.py`) is done here once for every phase-4 module: the repository root is
appended, so `pipeline.*` (the sentence splitter, the country lookup, `training_corpus`) resolves
from any working directory. Appended, not inserted, so nothing under the root can shadow `phase3`
or `phase4`.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

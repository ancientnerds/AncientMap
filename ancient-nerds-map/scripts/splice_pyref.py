# SPDX-License-Identifier: AGPL-3.0-only
"""Hydration-gate helper (react-ssr Task 15): splice the SSR-rendered pyref
pages (scripts/render_pyref.mjs output on stdin) into the built shell via
pipeline/app_shell.render_app_shell — the exact splice ssr_shell_response()
uses in production — and write dist/hydr_{name}.html for a static server.

    node scripts/render_pyref.mjs | python scripts/splice_pyref.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from pipeline import app_shell  # noqa: E402

app_shell.FRONTEND_DIR = REPO / "ancient-nerds-map" / "dist"

# Read stdin as bytes: on Windows the text stream decodes with cp1252 and
# mangles the UTF-8 node output (emoji → lone surrogates).
pages = json.loads(sys.stdin.buffer.read())
for name, page in pages.items():
    doc = app_shell.render_app_shell(
        page["entry"],
        head_html=page["head"],
        root_html=page["html"],
        route=json.dumps(page["route"], ensure_ascii=False).replace("<", "\\u003c"),
    )
    out = app_shell.FRONTEND_DIR / f"hydr_{name}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}")

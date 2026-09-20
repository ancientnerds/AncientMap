# SPDX-License-Identifier: AGPL-3.0-only
"""scripts/funnel_report.py — die Discord-Klicks aus dem API-Log.

Die Zeilen sind die, die api/routes/goto.py schreibt. Seit 2026-09-19 trägt
jede ihren UTC-Zeitpunkt; ohne ihn ist eine Zeile keinem Fenster zuzuordnen
und wird nicht gezählt.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

# By file: a dependency installs a top-level package named `scripts` into
# site-packages, which shadows our scripts/ directory for a plain import.
_SPEC = importlib.util.spec_from_file_location(
    "funnel_report", Path(__file__).resolve().parents[2] / "scripts" / "funnel_report.py"
)
assert _SPEC is not None and _SPEC.loader is not None
fr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fr)


def _line(src: str, bot: int, at: str) -> str:
    return f"INFO | api.routes.goto | goto_discord src={src} bot={bot} at={at}"


def test_clicks_carry_source_bot_flag_and_moment():
    clicks = fr.parse_clicks(
        [
            _line("seo", 0, "2026-09-19T08:12:33+00:00"),
            _line("landing", 1, "2026-09-19T09:00:00+00:00"),
            "INFO | api.main | something else entirely",
        ]
    )
    assert [(c.src, c.bot) for c in clicks] == [("seo", False), ("landing", True)]
    assert clicks[0].at == datetime(2026, 9, 19, 8, 12, 33, tzinfo=UTC)


def test_a_line_without_a_timestamp_is_not_counted():
    """Die 29 Zeilen aus der Zeit vor 2026-09-19 tragen keine Zeit (api/main.py
    formatiert ohne asctime). Sie in eine "letzte 24 h"-Tabelle zu zählen wäre
    genau die Falschaussage, wegen der der Stempel dazukam."""
    assert fr.parse_clicks(["INFO | api.routes.goto | goto_discord src=seo bot=1"]) == []


def test_the_json_file_driver_shape_is_read_too():
    raw = json.dumps({"log": _line("app", 0, "2026-09-19T10:00:00+00:00") + "\n"})
    clicks = fr.parse_clicks([raw])
    assert [c.src for c in clicks] == ["app"]


def test_the_table_counts_humans_and_bots_and_names_the_span(capsys):
    fr.print_table(
        [
            fr.Click("seo", False, datetime(2026, 9, 19, 8, 0, tzinfo=UTC)),
            fr.Click("seo", True, datetime(2026, 9, 19, 12, 0, tzinfo=UTC)),
            fr.Click("landing", False, datetime(2026, 9, 19, 6, 0, tzinfo=UTC)),
        ]
    )
    out = capsys.readouterr().out
    # Der Zeitraum, den die Zeilen wirklich abdecken — nicht der erfragte.
    assert "clicks from 2026-09-19T06:00:00+00:00 to 2026-09-19T12:00:00+00:00" in out
    assert "seo                1       1       2" in out
    assert "total              2       1       3" in out


def test_an_empty_window_says_so(capsys):
    fr.print_table([])
    assert "(no goto_discord entries in the given window)" in capsys.readouterr().out

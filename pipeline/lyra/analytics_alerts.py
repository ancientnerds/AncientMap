# SPDX-License-Identifier: AGPL-3.0-only
"""Discord-Alarme und Wochendigest aus den Umami-Daten (Plan Teil D).

Zwei Orchestrator-Schritte, beide billig genug für jeden Zyklus:

* ``check_hourly()`` — sieht die letzte Stunde auf ``js_error``-Häufungen durch
  und meldet eine Spitze sofort.
* ``weekly_digest()`` — montags zwischen 06:00 und 06:59 UTC einmal: Puls der
  Woche gegen die Vorwoche, die drei meistgeöffneten Sites, die drei
  meistgelesenen Stories, die drei größten Probleme und jeder Freitext aus dem
  Feedback der Woche.

Ohne ``DISCORD_WEBHOOK_URL`` tun beide nichts (einmal INFO im Log). Keiner der
beiden darf in den Zyklus hineinwerfen: eine tote Umami-Verbindung ist kein
Grund, den Rest der Pipeline zu stoppen.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from pipeline.lyra.orchestrator import _load_step_state, _save_step_state
from pipeline.stats_analysis import problems, sessions_from_rows
from pipeline.umami_db import (
    SQL_CONTENT,
    SQL_ERRORS,
    SQL_FEEDBACK,
    SQL_NOT_FOUND,
    SQL_OVERVIEW,
    SQL_SESSION_EVENTS,
    SQL_VITALS,
    fetch,
)
from pipeline.utils.notify import DISCORD_LIMIT, split_message

logger = logging.getLogger(__name__)

#: So viele gleiche js_error-Ereignisse in einer Stunde sind eine Spitze. Ein
#: einzelner kaputter Browser erzeugt Handvoll-Zahlen; 10 heisst, es trifft
#: mehrere Besucher.
ERROR_THRESHOLD = 10


WEEK = timedelta(days=7)
#: Montag 06:xx UTC — das Journal geht montags 06:00 UTC raus, der Digest
#: beschreibt dieselbe Woche.
DIGEST_HOUR = 6
#: Schlüssel in /app/logs/lyra_step_state.json (Epoch-Sekunden des Versands).
DIGEST_STATE_KEY = "digest_sent"

#: Der Hinweis auf den fehlenden Webhook steht einmal im Log, nicht stündlich.
_webhook_note_logged = False


def _webhook_configured() -> bool:
    global _webhook_note_logged
    if os.getenv("DISCORD_WEBHOOK_URL", "").strip():
        return True
    if not _webhook_note_logged:
        logger.info("[alerts] DISCORD_WEBHOOK_URL nicht gesetzt — Alarme und Digest bleiben aus")
        _webhook_note_logged = True
    return False


def _post(payload: dict[str, Any]) -> bool:
    """Eine Discord-Nachricht rausschicken.

    Der Import steht absichtlich in der Funktion: ``api/__init__.py`` zieht
    ``api.main`` nach und damit markdown/nh3, die das Lyra-Image nicht hat —
    ein Modulimport würde den Orchestrator am Starten hindern. Gleiches
    Muster wie in ``pipeline.lyra.curator``.
    """
    from pipeline.utils.notify import send_discord_webhook

    return send_discord_webhook(payload)


# ---------------------------------------------------------------------------
# Stündlicher Alarm
# ---------------------------------------------------------------------------


def error_spike_message(rows: list[dict[str, Any]], threshold: int = ERROR_THRESHOLD) -> str | None:
    """Discord-Text für alle Fehlergruppen ab ``threshold`` Treffern, sonst None.

    ``rows`` sind Zeilen der js_error-Abfrage: message, page, n.
    """
    spikes = sorted(
        (r for r in rows if int(r["n"] or 0) >= threshold),
        key=lambda r: int(r["n"] or 0),
        reverse=True,
    )
    if not spikes:
        return None
    lines = ["**JS-Fehler häufen sich** (letzte Stunde)"]
    lines += [f"- {r['n']}x auf {r['page']}: `{r['message']}`" for r in spikes[:5]]
    return "\n".join(lines)


def check_hourly() -> int:
    """Ein Zyklus Fehlerwache: die letzte Stunde prüfen, bei einer Spitze eine
    Nachricht posten. Rückgabe = Zahl der abgeschickten Nachrichten."""
    if not _webhook_configured():
        return 0
    try:
        until = datetime.now(UTC)
        rows = fetch(SQL_ERRORS, until - timedelta(hours=1), until)
        message = error_spike_message(rows)
        if message is None:
            return 0
        return 1 if _post({"content": message}) else 0
    except Exception:
        # Vertrag: der Schritt meldet 0 und der Zyklus läuft weiter. Die
        # Ursache steht mit Traceback im Lyra-Log.
        logger.exception("[alerts] Fehlerwache abgebrochen")
        return 0


# ---------------------------------------------------------------------------
# Wochendigest
# ---------------------------------------------------------------------------


def digest_due(now: datetime, last_sent: datetime | None) -> bool:
    """Montags 06:00-06:59 UTC und heute noch nicht verschickt."""
    if now.weekday() != 0 or now.hour != DIGEST_HOUR:
        return False
    return last_sent is None or last_sent.date() < now.date()


def _delta(current: int, previous: int) -> str:
    """ "+20 %" gegen die Vorwoche — ohne Vorwoche gibt es keinen Vergleich."""
    if not previous:
        return "Vorwoche 0"
    pct = round((current - previous) / previous * 100)
    sign = "+" if pct > 0 else ""
    return f"Vorwoche {previous}, {sign}{pct} %"


def _top(content: list[dict[str, Any]], event_name: str, limit: int = 3) -> list[dict[str, Any]]:
    rows = [r for r in content if r["event_name"] == event_name]
    return sorted(rows, key=lambda r: int(r["n"] or 0), reverse=True)[:limit]


def problem_lines(problem_rows: list[dict[str, Any]], limit: int = 3) -> list[str]:
    """Die größten Probleme der Woche als Zeilen — dieselbe Rangfolge, die das
    Dashboard zeigt (pipeline.stats_analysis.problems), damit Digest und Panel
    nie zwei Wahrheiten erzählen."""
    labels = {
        "js_error": "JS-Fehler",
        "slow_page": "Langsame Seite",
        "broken_link": "Toter Link",
        "shallow_exit": "Absprung",
        "empty_search": "Suche ohne Treffer",
    }
    lines = []
    for p in problem_rows[:limit]:
        kind = labels.get(str(p.get("kind")), str(p.get("kind")))
        detail = str(p.get("detail") or "").strip()
        lines.append(f"{kind}: {p.get('label')}" + (f" — {detail}" if detail else ""))
    return lines


def _section(title: str, lines: list[str]) -> str:
    return "\n".join([f"**{title}**", *(lines or ["(nichts)"])])


def digest_message(
    now: datetime,
    this_week: dict[str, Any],
    last_week: dict[str, Any],
    content: list[dict[str, Any]],
    problem_rows: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> str:
    """Der ganze Digest als ein Text; das Aufteilen macht ``_split_message``."""
    sites = [
        f"{i}. {r['label']}" + (f" ({r['country']})" if r["country"] else "") + f" — {r['n']}x"
        for i, r in enumerate(_top(content, "site_open"), start=1)
    ]
    stories = [
        f"{i}. {r['label']} — {r['n']}x" for i, r in enumerate(_top(content, "story_open"), start=1)
    ]
    ranked = [f"{i}. {line}" for i, line in enumerate(problem_lines(problem_rows), start=1)]
    texts = [r for r in feedback if (r["text"] or "").strip()]
    voices = [
        f"- [{r['prompt']}/{r['answer']}] {r['text'].strip()} — {r['url_path']}" for r in texts
    ]
    return "\n\n".join(
        [
            f"**Founders-Digest {now:%d.%m.%Y}** — die letzten 7 Tage",
            "\n".join(
                [
                    f"Aufrufe: {this_week['views']} ({_delta(this_week['views'], last_week['views'])})",  # noqa: E501
                    f"Sessions: {this_week['sessions']} ({_delta(this_week['sessions'], last_week['sessions'])})",  # noqa: E501
                ]
            ),
            _section("Meistgeöffnete Sites", sites),
            _section("Meistgelesene Stories", stories),
            _section("Größte Probleme", ranked),
            _section(f"Feedback der Woche ({len(voices)})", voices),
        ]
    )


def weekly_digest(now: datetime | None = None) -> int:
    """Montagsdigest. Rückgabe = Zahl der abgeschickten Discord-Nachrichten
    (ein langer Digest geht in mehreren Teilen raus).

    ``now`` spritzen die Tests ein; der Orchestrator ruft ohne Argument auf.
    """
    if not _webhook_configured():
        return 0
    try:
        now = now or datetime.now(UTC)
        stamp = _load_step_state().get(DIGEST_STATE_KEY)
        if not digest_due(now, datetime.fromtimestamp(stamp, UTC) if stamp else None):
            return 0
        week_start = now - WEEK
        # live= wird für den Puls nicht gebraucht (SQL_OVERVIEW zählt damit die
        # Sessions der letzten Minuten) — das Fensterende schaltet ihn ab.
        this_week = fetch(SQL_OVERVIEW, week_start, now, live=now)[0]
        last_week = fetch(SQL_OVERVIEW, week_start - WEEK, week_start, live=week_start)[0]
        content = fetch(SQL_CONTENT, week_start, now)
        feedback = fetch(SQL_FEEDBACK, week_start, now)
        # Same four inputs the dashboard's Problems panel uses.
        ranked = problems(
            sessions_from_rows(fetch(SQL_SESSION_EVENTS, week_start, now)),
            not_found=fetch(SQL_NOT_FOUND, week_start, now),
            vitals=fetch(SQL_VITALS, week_start, now),
            errors=fetch(SQL_ERRORS, week_start, now),
            searches=[r for r in content if r["event_name"] == "search"],
        )
        message = digest_message(now, this_week, last_week, content, ranked, feedback)
        posted = sum(1 for chunk in split_message(message) if _post({"content": chunk}))
        if posted:
            # Frisch laden: die Datei gehört auch den Intervallschritten.
            state = _load_step_state()
            state[DIGEST_STATE_KEY] = now.timestamp()
            _save_step_state(state)
        return posted
    except Exception:
        logger.exception("[alerts] Wochendigest abgebrochen")
        return 0

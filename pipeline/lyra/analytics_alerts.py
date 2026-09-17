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
from pipeline.umami_db import SQL_CONTENT, SQL_FEEDBACK, SQL_OVERVIEW, fetch

logger = logging.getLogger(__name__)

#: Teil C legt dieselbe Abfrage als ``pipeline.umami_db.SQL_ERRORS`` an. Beide
#: Teile entstehen parallel, deshalb hier eine eigene Kopie mit identischem
#: Text: beim Zusammenführen ersetzt ein Import aus ``pipeline.umami_db``
#: diese Konstante ersatzlos.
_SQL_ERRORS_LOCAL = """
SELECT max(m.string_value) AS message, max(p.string_value) AS page, count(*) AS n
FROM website_event e
JOIN event_data m ON m.website_event_id = e.event_id AND m.data_key = 'message'
JOIN event_data p ON p.website_event_id = e.event_id AND p.data_key = 'page'
WHERE e.website_id = :website_id AND e.event_name = 'js_error'
  AND e.created_at >= :since AND e.created_at < :until
GROUP BY m.string_value, p.string_value ORDER BY n DESC LIMIT 30
"""

#: So viele gleiche js_error-Ereignisse in einer Stunde sind eine Spitze. Ein
#: einzelner kaputter Browser erzeugt Handvoll-Zahlen; 10 heisst, es trifft
#: mehrere Besucher.
ERROR_THRESHOLD = 10

#: Discords Nachrichtenlimit ist 2000 Zeichen; 1900 lässt Luft für Anhänge am
#: Zeilenende. Gleicher Wert wie in api/services/discord_bot.py.
DISCORD_LIMIT = 1900

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
    from api.services.notify import send_discord_webhook

    return send_discord_webhook(payload)


def _split_message(message: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Teilt an Absatz, sonst Zeile, sonst Leerzeichen, sonst hart — Algorithmus
    von ``api.services.discord_bot._split_response``.

    Nicht importiert, sondern nachgebaut: ``discord_bot`` importiert die
    discord-Bibliothek beim Modulimport (und ``api/__init__`` die ganze API),
    beides existiert im Lyra-Container nicht.
    """
    if len(message) <= limit:
        return [message]
    chunks: list[str] = []
    rest = message
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        split = rest.rfind("\n\n", 0, limit)
        if split == -1:
            split = rest.rfind("\n", 0, limit)
        if split == -1:
            split = rest.rfind(" ", 0, limit)
        if split == -1:
            split = limit
        chunks.append(rest[:split])
        rest = rest[split:].lstrip()
    return chunks


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
        rows = fetch(_SQL_ERRORS_LOCAL, until - timedelta(hours=1), until)
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


def problem_lines(
    errors: list[dict[str, Any]], content: list[dict[str, Any]], limit: int = 3
) -> list[str]:
    """Die größten Probleme der Woche, gewichtet wie im Dashboard: ein
    JS-Fehler wiegt dreifach, eine Suche ohne Treffer einfach.

    Teil C baut dieselbe Rangfolge als ``founders_stats.problems()`` mit mehr
    Quellen (404er, Web Vitals, flache Ausstiege); beim Zusammenführen ersetzt
    sie diese drei Zeilen.
    """
    scored: list[tuple[int, str]] = []
    for r in errors:
        n = int(r["n"] or 0)
        scored.append((n * 3, f"JS-Fehler auf {r['page']}: `{r['message']}` ({n}x)"))
    for r in content:
        if r["event_name"] == "search" and not (r["results"] or 0):
            n = int(r["n"] or 0)
            scored.append((n, f'Suche ohne Treffer: "{r["label"]}" ({n}x)'))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return [line for _, line in scored[:limit]]


def _section(title: str, lines: list[str]) -> str:
    return "\n".join([f"**{title}**", *(lines or ["(nichts)"])])


def digest_message(
    now: datetime,
    this_week: dict[str, Any],
    last_week: dict[str, Any],
    content: list[dict[str, Any]],
    errors: list[dict[str, Any]],
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
    problems = [f"{i}. {line}" for i, line in enumerate(problem_lines(errors, content), start=1)]
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
            _section("Größte Probleme", problems),
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
        errors = fetch(_SQL_ERRORS_LOCAL, week_start, now)
        feedback = fetch(SQL_FEEDBACK, week_start, now)
        message = digest_message(now, this_week, last_week, content, errors, feedback)
        posted = sum(1 for chunk in _split_message(message) if _post({"content": chunk}))
        if posted:
            # Frisch laden: die Datei gehört auch den Intervallschritten.
            state = _load_step_state()
            state[DIGEST_STATE_KEY] = now.timestamp()
            _save_step_state(state)
        return posted
    except Exception:
        logger.exception("[alerts] Wochendigest abgebrochen")
        return 0

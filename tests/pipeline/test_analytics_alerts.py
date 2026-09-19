# SPDX-License-Identifier: AGPL-3.0-only
"""Discord-Alarme und Wochendigest (Plan Teil D, Task D1).

Datenbanklos: ``aa.fetch`` (pipeline.umami_db.fetch) wird durch eine Attrappe
ersetzt, die je SQL-Konstante Zeilen liefert, und ``aa._post`` sammelt die
Nachrichten statt sie an Discord zu schicken.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import pipeline.lyra.analytics_alerts as aa
import pipeline.lyra.orchestrator as orch
from pipeline.umami_db import SQL_CONTENT, SQL_ERRORS, SQL_FEEDBACK, SQL_OVERVIEW

MONDAY_6 = datetime(2026, 9, 21, 6, 10, tzinfo=UTC)


class Fetch:
    """fetch()-Attrappe: Zeilen je SQL-Text, gemerkte Aufrufe.

    Der Wert darf eine Liste sein oder ein Callable (since, until) -> Zeilen —
    SQL_OVERVIEW wird zweimal gefragt (diese Woche, Vorwoche).
    """

    def __init__(self, rows_by_sql: dict[str, Any] | None = None):
        self.rows_by_sql = rows_by_sql or {}
        self.calls: list[tuple[str, datetime, datetime, dict]] = []

    def __call__(self, sql, since, until, **params):
        self.calls.append((sql, since, until, params))
        rows = self.rows_by_sql.get(sql, [])
        return rows(since, until) if callable(rows) else list(rows)


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")


@pytest.fixture
def posted(monkeypatch) -> list[dict]:
    """Sammelt die Payloads; _post meldet Erfolg wie ein 204 von Discord."""
    sent: list[dict] = []
    monkeypatch.setattr(aa, "_post", lambda payload: bool(sent.append(payload) or True))
    return sent


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Der Digest merkt sich seinen Versand in der Schrittstatusdatei."""
    path = tmp_path / "logs" / "lyra_step_state.json"
    monkeypatch.setattr(orch, "STEP_STATE_FILE", path)
    return path


def content_row(event_name: str, label: str, n: int, country=None, results=None) -> dict[str, Any]:
    """Eine Zeile von SQL_CONTENT."""
    return {
        "event_name": event_name,
        "label": label,
        "country": country,
        "results": results,
        "n": n,
    }


def feedback_row(text: str | None, url_path: str = "/sites/peru/x-1") -> dict[str, Any]:
    """Eine Zeile von SQL_FEEDBACK."""
    return {
        "created_at": MONDAY_6,
        "url_path": url_path,
        "prompt": "site_page",
        "answer": "no",
        "text": text,
    }


def _digest_fetch(**overrides: Any) -> Fetch:
    rows = {
        SQL_OVERVIEW: lambda since, until: (
            [{"views": 1200, "sessions": 300, "live_sessions": 0}]
            if until == MONDAY_6
            else [{"views": 1000, "sessions": 250, "live_sessions": 0}]
        ),
        SQL_CONTENT: [
            content_row("site_open", "Göbekli Tepe", 42, country="Türkiye"),
            content_row("site_open", "Giza", 30, country="Egypt"),
            content_row("site_open", "Stonehenge", 20, country="UK"),
            content_row("site_open", "Nazca", 10, country="Peru"),
            content_row("story_open", "Neue Datierung", 9),
            content_row("story_open", "Tempelfund", 5),
            content_row("search", "atlantis", 7, results=0),
            content_row("search", "giza", 4, results=12),
        ],
        SQL_FEEDBACK: [
            feedback_row("Koordinaten stimmen nicht"),
            feedback_row(None, url_path="/lyra.html"),
        ],
        SQL_ERRORS: [{"message": "x is not a function", "page": "globe", "n": 12, "sessions": 5}],
    }
    rows.update(overrides)
    return Fetch(rows)


# ---- Fehlerspitze ---------------------------------------------------------


def test_error_spike_message_names_page_and_affected_visitors():
    msg = aa.error_spike_message(
        [{"message": "x is not a function", "page": "globe", "n": 14, "sessions": 4}], threshold=3
    )
    assert msg is not None
    assert "4 visitors" in msg and "14" in msg and "globe" in msg
    assert "x is not a function" in msg


def test_no_message_below_threshold():
    """One browser reloading a broken page four times makes twelve events and
    one session — the threshold counts sessions so that stays quiet."""
    loud = [{"message": "m", "page": "p", "n": 12, "sessions": 1}]
    assert aa.error_spike_message(loud, threshold=3) is None
    assert aa.error_spike_message([], threshold=3) is None


def test_check_hourly_posts_the_spike_for_the_last_hour(webhook, posted, monkeypatch):
    fetch = Fetch({SQL_ERRORS: [{"message": "boom", "page": "globe", "n": 11, "sessions": 4}]})
    monkeypatch.setattr(aa, "fetch", fetch)
    assert aa.check_hourly() == 1
    assert len(posted) == 1 and "boom" in posted[0]["content"]
    _, since, until, _ = fetch.calls[0]
    assert until - since == timedelta(hours=1)


def test_check_hourly_stays_quiet_below_the_threshold(webhook, posted, monkeypatch):
    rows = [{"message": "b", "page": "g", "n": 2, "sessions": 2}]
    monkeypatch.setattr(aa, "fetch", Fetch({SQL_ERRORS: rows}))
    assert aa.check_hourly() == 0
    assert posted == []


# ---- Digest-Fenster -------------------------------------------------------


def test_digest_is_due_only_once_on_monday_morning():
    assert aa.digest_due(MONDAY_6, last_sent=None)
    assert not aa.digest_due(MONDAY_6, last_sent=MONDAY_6.replace(minute=5))
    assert not aa.digest_due(datetime(2026, 9, 22, 6, 10, tzinfo=UTC), last_sent=None)
    assert not aa.digest_due(MONDAY_6.replace(hour=7), last_sent=None)
    assert aa.digest_due(MONDAY_6 + timedelta(days=7), last_sent=MONDAY_6)


# ---- Ohne Webhook: lautloser No-Op ---------------------------------------


def test_without_a_webhook_nothing_is_queried_and_nothing_posted(monkeypatch, state_file):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    def explode(*_a, **_k):
        raise AssertionError("ohne Webhook darf keine Abfrage laufen")

    monkeypatch.setattr(aa, "fetch", explode)
    monkeypatch.setattr(aa, "_post", explode)
    assert aa.check_hourly() == 0
    assert aa.weekly_digest(now=MONDAY_6) == 0
    assert not state_file.exists()


# ---- Fehler dürfen den Zyklus nicht treffen -------------------------------


def test_a_failing_query_does_not_reach_the_orchestrator(webhook, posted, monkeypatch, state_file):
    def boom(*_a, **_k):
        raise RuntimeError("umami down")

    monkeypatch.setattr(aa, "fetch", boom)
    assert aa.check_hourly() == 0
    assert aa.weekly_digest(now=MONDAY_6) == 0
    assert posted == []


# ---- Digest-Inhalt --------------------------------------------------------


def test_digest_carries_pulse_top_content_problems_and_every_feedback_text(
    webhook, posted, monkeypatch, state_file
):
    monkeypatch.setattr(aa, "fetch", _digest_fetch())
    assert aa.weekly_digest(now=MONDAY_6) == 1
    text = posted[0]["content"]
    assert "1200" in text and "1000" in text and "20 %" in text  # Puls gegen die Vorwoche
    assert "Göbekli Tepe" in text and "Giza" in text and "Stonehenge" in text
    assert "Nazca" not in text  # nur die drei meistgeöffneten
    assert "Neue Datierung" in text and "Tempelfund" in text
    assert "x is not a function" in text and "atlantis" in text  # Probleme
    assert "Koordinaten stimmen nicht" in text  # jeder Freitext der Woche


def test_digest_asks_for_seven_days_and_the_seven_before(webhook, posted, monkeypatch, state_file):
    fetch = _digest_fetch()
    monkeypatch.setattr(aa, "fetch", fetch)
    aa.weekly_digest(now=MONDAY_6)
    pulse = [c for c in fetch.calls if c[0] is SQL_OVERVIEW]
    assert len(pulse) == 2
    (_, this_since, this_until, _), (_, prev_since, prev_until, _) = pulse
    assert this_until == MONDAY_6 and this_until - this_since == timedelta(days=7)
    assert prev_until == this_since and prev_until - prev_since == timedelta(days=7)


# ---- Chunking -------------------------------------------------------------


def test_split_message_at_the_discord_boundary():
    assert aa.split_message("x" * aa.DISCORD_LIMIT) == ["x" * aa.DISCORD_LIMIT]
    chunks = aa.split_message("x" * (aa.DISCORD_LIMIT + 1))
    assert len(chunks) == 2 and all(len(c) <= aa.DISCORD_LIMIT for c in chunks)
    assert "".join(chunks) == "x" * (aa.DISCORD_LIMIT + 1)


def test_a_long_digest_goes_out_in_chunks_under_the_limit(webhook, posted, monkeypatch, state_file):
    many = [
        feedback_row(f"Rückmeldung {i} " + "sehr ausführlich " * 10, url_path=f"/sites/peru/x-{i}")
        for i in range(60)
    ]
    monkeypatch.setattr(aa, "fetch", _digest_fetch(**{SQL_FEEDBACK: many}))
    n = aa.weekly_digest(now=MONDAY_6)
    assert n > 1 and n == len(posted)
    assert all(len(p["content"]) <= aa.DISCORD_LIMIT for p in posted)
    joined = "".join(p["content"] for p in posted)
    assert "Rückmeldung 0 " in joined and "Rückmeldung 59 " in joined


# ---- Persistenz -----------------------------------------------------------


def test_digest_sent_is_persisted_and_honoured(webhook, posted, monkeypatch, state_file):
    monkeypatch.setattr(aa, "fetch", _digest_fetch())
    assert aa.weekly_digest(now=MONDAY_6) == 1
    assert json.loads(state_file.read_text(encoding="utf-8"))["digest_sent"] == MONDAY_6.timestamp()

    posted.clear()
    assert aa.weekly_digest(now=MONDAY_6 + timedelta(minutes=20)) == 0
    assert posted == []

    assert aa.weekly_digest(now=MONDAY_6 + timedelta(days=7)) == 1


def test_digest_keeps_the_interval_steps_timestamps(webhook, posted, monkeypatch, state_file):
    """Der Digest schreibt dieselbe Datei wie die Intervallschritte — er darf
    deren Zeitstempel nicht überschreiben (er läuft als letzter im Zyklus)."""
    monkeypatch.setattr(aa, "fetch", _digest_fetch())
    orch._save_step_state({"library": 111.0})
    aa.weekly_digest(now=MONDAY_6)
    assert orch._load_step_state()["library"] == 111.0


# ---- Registrierung im Orchestrator ---------------------------------------


def test_steps_are_registered_after_indexnow():
    for name, func in (("alerts", "check_hourly"), ("digest", "weekly_digest")):
        module_path, func_name, needs_settings, desc = orch.STEPS[name]
        assert module_path == "pipeline.lyra.analytics_alerts"
        assert func_name == func and needs_settings is False
        assert desc.format(n=2).endswith("2 posted")
        assert name not in orch.STEP_INTERVALS  # jeder Zyklus, beide sind billig
    assert orch.STEP_ORDER[-3:] == ["indexnow", "alerts", "digest"]

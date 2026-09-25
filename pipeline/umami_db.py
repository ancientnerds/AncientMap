# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only access to Umami's tables for the founders dashboard and the
alerts. Same Postgres as everything else, its own database ``umami``, its own
role (UMAMI_DB_PASSWORD from the VPS .env). Every query is parameterised and
scoped to one website and a half-open time window [:since, :until); nothing
here writes.

Umami 3 columns this relies on (verified on production, 2026-09-17):
``website_event`` (event_id, website_id, session_id, created_at, url_path,
referrer_domain, utm_source, event_type, event_name), ``event_data``
(website_event_id, data_key, string_value, number_value) and ``session``
(session_id, country, city, device, browser, screen, os, language).
event_type 1 = pageview, 2 = custom event.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from pipeline.config import settings

#: The Umami website whose events we read — the same id the tracker tag carries.
logger = logging.getLogger(__name__)

WEBSITE_ID = os.getenv("VITE_UMAMI_WEBSITE_ID", "")


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Lazy: importing this module never connects; the first query does.
    A missing UMAMI_DB_PASSWORD is a misconfigured deploy and fails loudly."""
    password = os.environ["UMAMI_DB_PASSWORD"]
    url = URL.create(
        "postgresql",
        username="umami",
        password=password,
        host=settings.database.host,
        port=settings.database.port,
        database="umami",
    )
    return create_engine(url, pool_pre_ping=True, pool_size=2, connect_args={"connect_timeout": 10})


SQL_OVERVIEW = """
SELECT
  count(*) FILTER (WHERE event_type = 1)                        AS views,
  count(DISTINCT session_id)                                    AS sessions,
  count(DISTINCT session_id) FILTER (WHERE created_at >= :live) AS live_sessions
FROM website_event
WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
"""

SQL_MAP = """
SELECT s.country, s.city, date_part('hour', e.created_at AT TIME ZONE 'UTC')::int AS hour,
       count(DISTINCT e.session_id) AS sessions
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.event_type = 1
  AND e.created_at >= :since AND e.created_at < :until
GROUP BY 1, 2, 3
"""

SQL_SESSION_EVENTS = """
SELECT e.session_id, e.created_at, e.event_type, e.event_name, e.url_path, e.referrer_domain,
       e.utm_source, s.country, s.device, s.browser,
       (SELECT jsonb_object_agg(d.data_key, coalesce(d.string_value, d.number_value::text))
          FROM event_data d WHERE d.website_event_id = e.event_id) AS data
FROM website_event e JOIN session s ON s.session_id = e.session_id
WHERE e.website_id = :website_id AND e.created_at >= :since AND e.created_at < :until
ORDER BY e.session_id, e.created_at
"""

#: Two levels: first one row per event (event_data is key-value, so a site's
#: name and its country live in separate rows), then the ranking. Without the
#: first level a site would lose its country and a search its result count.
SQL_CONTENT = """
WITH ev AS (
    SELECT
        e.event_id,
        e.event_name,
        max(d.string_value) FILTER (
            WHERE d.data_key IN ('name', 'story', 'paper', 'q')
        ) AS label,
        max(d.string_value) FILTER (WHERE d.data_key = 'country') AS country,
        max(d.number_value) FILTER (WHERE d.data_key = 'results') AS results,
        e.session_id, e.created_at, s.country AS visitor_country,
        s.device, s.browser
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_type = 2
      AND e.created_at >= :since AND e.created_at < :until
      AND e.event_name IN ('site_open', 'story_open', 'paper_open', 'search')
    GROUP BY e.event_id, e.event_name, e.session_id, e.created_at,
             s.country, s.device, s.browser
)
SELECT
    event_name,
    label,
    max(country) AS country,
    -- max, not min: one zero-result run (a search fired before the site
    -- data finished loading) would otherwise brand the most successful
    -- term on the site as "never finds anything".
    max(results) AS results,
    count(*) AS n,
    max(created_at) AS last_at,
    (array_agg(session_id::text    ORDER BY created_at DESC))[1] AS last_session,
    (array_agg(visitor_country     ORDER BY created_at DESC))[1] AS last_country,
    (array_agg(device              ORDER BY created_at DESC))[1] AS last_device,
    (array_agg(browser             ORDER BY created_at DESC))[1] AS last_browser
FROM ev
WHERE label IS NOT NULL AND label <> ''
GROUP BY event_name, label
ORDER BY n DESC
LIMIT 300
"""

#: The rated thing travels in the same event (ThumbsFeedback's `extra`): a
#: site id with its country, a story id, a paper or journal slug. Without it
#: the inbox can only say "somewhere on a site page".
SQL_FEEDBACK = """
SELECT e.created_at, e.url_path,
       max(d.string_value) FILTER (WHERE d.data_key = 'prompt')  AS prompt,
       max(d.string_value) FILTER (WHERE d.data_key = 'answer')  AS answer,
       max(d.string_value) FILTER (WHERE d.data_key = 'text')    AS text,
       max(d.string_value) FILTER (WHERE d.data_key = 'site')    AS site,
       max(d.string_value) FILTER (WHERE d.data_key = 'country') AS country,
       max(d.string_value) FILTER (WHERE d.data_key = 'paper')   AS paper,
       max(d.string_value) FILTER (WHERE d.data_key = 'journal') AS journal,
       max(coalesce(d.string_value, d.number_value::text))
           FILTER (WHERE d.data_key = 'story')                   AS story
FROM website_event e JOIN event_data d ON d.website_event_id = e.event_id
WHERE e.website_id = :website_id AND e.event_name = 'feedback'
  AND e.created_at >= :since AND e.created_at < :until
GROUP BY e.event_id, e.created_at, e.url_path ORDER BY e.created_at DESC LIMIT 200
"""

SQL_SOURCES = """
SELECT coalesce(nullif(utm_source, ''), nullif(referrer_domain, ''), 'direct') AS source,
       count(DISTINCT session_id) AS sessions,
       -- Page views as well as sessions, so the panel can put Umami's number
       -- next to nginx's, which counts requests. Measured 2026-09-19 over the
       -- same window: nginx answered 189 Google page arrivals (168 with a 200,
       -- 21 with a 410) while Umami recorded 62 views from 51 sessions. The
       -- gap is the panel's whole point.
       count(*) AS views
FROM website_event
WHERE website_id = :website_id AND event_type = 1
  AND created_at >= :since AND created_at < :until
GROUP BY 1 ORDER BY 2 DESC LIMIT 40
"""

#: When it last happened and to whom — the founders' first two questions about
#: anything on the problems panel (owner, 2026-09-19). Cookieless analytics has
#: no user: the visitor is the session Umami recognises for one calendar month,
#: shown as its country, device, browser and the first eight characters of that
#: id. Every problem query selects this block over an `ev` CTE that carries
#: created_at, session_id, country, device and browser.
_LAST_VISITOR = """       max(created_at) AS last_at,
       (array_agg(session_id::text ORDER BY created_at DESC))[1] AS last_session,
       (array_agg(country          ORDER BY created_at DESC))[1] AS last_country,
       (array_agg(device           ORDER BY created_at DESC))[1] AS last_device,
       (array_agg(browser          ORDER BY created_at DESC))[1] AS last_browser"""

#: Dead links. A pageview does not carry its HTTP status, so the 404 page says
#: so itself: one `not_found` event per view with the missing path and the
#: referrer's host (pipeline/article_html_renderer.py, _NOT_FOUND_FEEDBACK).
#: Two levels again — path and referrer are two event_data rows per event.
#: Both counts travel, exactly as in SQL_ERRORS: ``n`` is how often the dead
#: link was hit and is what the panel prints, ``sessions`` how many visitors
#: hit it and is what the score weighs — one person reloading a dead link ten
#: times is one broken link, not ten.
SQL_NOT_FOUND = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id, e.created_at, s.country, s.device, s.browser,
        max(d.string_value) FILTER (WHERE d.data_key = 'path')     AS path,
        max(d.string_value) FILTER (WHERE d.data_key = 'referrer') AS referrer
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'not_found'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser
)
SELECT path, coalesce(nullif(referrer, ''), 'direct') AS referrer, count(*) AS n,
       count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE path IS NOT NULL AND path <> ''
GROUP BY 1, 2
ORDER BY n DESC
LIMIT 50
"""
)

#: Core Web Vitals per page type: the 75th percentile is what Google reports
#: and what a visitor with a middling phone actually waits. `value` is a
#: number, so it lives in number_value; the cast keeps Postgres from handing
#: back a numeric that would serialise as a string.
#: `samples` and `sessions` are both needed and mean different things:
#: a percentile is only a percentile over enough *measurements*
#: (stats_analysis.VITAL_MIN_SAMPLES), while the panel's score weighs the
#: *visitors* it reached, like every other kind on that panel.
SQL_VITALS = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id, e.created_at, s.country, s.device, s.browser,
        max(d.string_value) FILTER (WHERE d.data_key = 'page')  AS page,
        max(d.string_value) FILTER (WHERE d.data_key = 'name')  AS name,
        max(d.number_value) FILTER (WHERE d.data_key = 'value') AS metric_value
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'vital'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser
)
SELECT
    page,
    name,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY metric_value::float8) AS p75,
    count(*) AS samples,
    count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE page IS NOT NULL AND name IS NOT NULL AND metric_value IS NOT NULL
GROUP BY 1, 2
ORDER BY samples DESC
LIMIT 60
"""
)

#: Uncaught JavaScript errors, grouped by message and page (src/analytics/boot.ts
#: clips the message to the tracker's 100 characters and the file name to 60).
#: Both counts travel: ``n`` is how often it fired, ``sessions`` how many
#: visitors it reached. One visitor reloading a broken page three times makes
#: nine events (boot.ts sends at most three per page view) and one session —
#: only the second number says how big the damage is.
SQL_ERRORS = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id,
        e.created_at,
        s.country, s.device, s.browser,
        max(d.string_value) FILTER (WHERE d.data_key = 'message') AS message,
        max(d.string_value) FILTER (WHERE d.data_key = 'page')    AS page
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'js_error'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser
)
SELECT message, coalesce(page, 'unknown') AS page, count(*) AS n,
       count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE message IS NOT NULL AND message <> ''
GROUP BY 1, 2
ORDER BY sessions DESC, n DESC
LIMIT 30
"""
)


#: The one path that hosts the globe. Verified 2026-09-19: exactly one
#: url_path contains "globe", all eight globe_ready events ever recorded fired
#: there, and no url_path carries a query string, so equality is exact.
GLOBE_PATH = "/globe.html"

#: How often the globe actually comes up, and how long it took when it did.
#: One row per session:
#:   views    - page views, one per document load. App.tsx never calls
#:              pushState (only AccountPage and ArticlesPage do), so Umami
#:              cannot manufacture a virtual view here and views and
#:              globe_ready are the same granularity.
#:   ready    - globe_ready, sent once per load by App (hooks/useGlobeReady.ts)
#:              when the loading overlay fades: the sites, the critical layers
#:              and the focus lookup are in, no error screen, a live context.
#:   ready_ms - the milliseconds each globe_ready carried, so the funnel and
#:              the times come from ONE scan. They include the sites payload
#:              and the focus lookup; the samples of the build before the
#:              globe-load deploy measured the layers moment only, and the
#:              measured_from cut below leaves them out.
#: The LEFT JOIN is load-bearing: a page view has no event_data row.
#: There is deliberately no "did the bundle boot" column. web-vitals' onTTFB
#: waits for document.readyState === 'complete', so a visitor who leaves
#: during a sixteen-second loading overlay reports no vital at all - counting
#: those loads out of the denominator would remove exactly the abandoners
#: this query exists to find (measured 2026-09-19: 6 of 33 loads).
#: globe_idle is not read either: markGlobeActivity() is called from three
#: places only, so a camera drag leaves the timer armed. Both live globe_idle
#: events carry the literal ms=30000 and both belong to a visitor who was
#: toggling a country filter at that moment. Precision 0/2.
#:
#: The same scan also says how the loads that never reached globe_ready
#: ended (stats_analysis.globe_funnel folds them; one query, because the
#: dashboard contract forbids a second /globe.html scan). The frontend sends
#: at most one ending per load; Umami has no page-load id, so the fold is per
#: session and capped by the unreached loads.
#:   gate_left     - globe_gate with a choice other than the globe: the phone
#:                   gate sent the visitor elsewhere.
#:   gate_quit     - globe_abandon{phase:'gate'}: left while the gate showed.
#:   unsupported   - globe_unsupported: the capability check failed.
#:   failed        - globe_error of the start. Background failures carry
#:                   phase 'bg:<task>' and failures after globe_ready carry
#:                   'live' (the error boundary caught a globe that was up,
#:                   or a loader failed later); both belong to loads that
#:                   reached the globe, so they are excluded. left(), because
#:                   a LIKE pattern needs the percent sign the guard test forbids.
#:                   So is a start failure marked ending='no': the load had
#:                   already ended (a tab switch while loading sent
#:                   globe_abandon, the visitor came back to the error
#:                   screen); it is sent for its phase and message only
#:                   (src/hooks/useGlobeScreenEnding.ts).
#:   context_lost  - webgl_lost{phase:'loading'}: the start failure the globe
#:                   reported before globe_error existed. Uncounted, it would
#:                   land in "no signal", which reads as a crash.
#:   abandoned     - globe_abandon in any phase after the gate.
#:   abandon_ms    - their ms, oldest first, so the fold keeps the latest. The
#:                   wait since the load started: navigation, or the moment
#:                   the phone gate went away (analytics/globeAbandon.ts
#:                   createLoadClock) - reading the gate is no loading wait.
#:                   ready_ms counts from navigation, the gate included.
#: Every column counts only the session's events from measured_from on, the
#: first load that ran the build with the endings (the globe-load deploy of
#: 2026-09-24). The loads before it are left out entirely, successes
#: included: the old build was a different product (a ~16 s load, its ready
#: measured the layers moment only) and sent no ending, so its unreached
#: loads could only read as crashes. The founders asked for it on 2026-09-25,
#: once the new build had proved itself. measured_from is the earlier of:
#:   - worker_from: endings_since, the first ending event ever recorded on
#:     the path (not the first in the window), the moment the instrumentation
#:     went live. For a session that opened the globe before it, the second
#:     view at or after it instead: the globe page installed the service
#:     worker, which serves globe.html and its JS cache-first, so the first
#:     load after the deploy still ran the previous build and the next one
#:     runs the new (src/pwa/globeStartPrecache.ts).
#:   - The session's last view at or before its own first ending: only the
#:     new build sends one, so that load ran it. This keeps the load that
#:     sent the very first ending (its view came before endings_since, live
#:     2026-09-24: 40 s before), and a first load after the deploy that
#:     another page had already switched to the new worker, whenever it
#:     ended without the globe.
#: Neither yet (no ending recorded, or an old session without a second view
#: and without an ending of its own): none of the session's events count.
#: Cut per load, not decided per session: an Umami session is one browser for
#: a calendar month, so it holds loads from both sides. Both CTEs read the
#: session's whole history on the path, not the window: the view before the
#: endings began can lie before :since. What this cannot see, so a stale first
#: load still counts: a browser whose earlier globe visit fell in an earlier
#: month (another Umami session), or whose worker came from another page. The
#: other way round, a session's first load after the deploy that already ran
#: the new build is left out when it reached the globe or went silent: only an
#: ending marks its build.
#: choice and phase are strings (event_data.string_value); ms is a number and
#: lives in number_value.
SQL_GLOBE = """
WITH first_ending AS (
    SELECT min(e2.created_at) AS endings_since
    FROM website_event e2
    WHERE e2.website_id = :website_id AND e2.url_path = :path
      AND e2.event_name IN ('globe_gate', 'globe_unsupported', 'globe_error', 'globe_abandon')
),
ev AS (
    SELECT e.event_id, e.session_id, e.created_at, e.event_type, e.event_name,
           (max(d.number_value) FILTER (WHERE d.data_key = 'ms'))::float8 AS ms,
           max(d.string_value) FILTER (WHERE d.data_key = 'choice') AS choice,
           max(d.string_value) FILTER (WHERE d.data_key = 'phase')  AS phase,
           max(d.string_value) FILTER (WHERE d.data_key = 'ending') AS ending
    FROM website_event e
    LEFT JOIN event_data d ON d.website_event_id = e.event_id
    WHERE e.website_id = :website_id AND e.url_path = :path
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, e.event_type, e.event_name
),
switched AS (
    SELECT v.session_id,
           CASE WHEN bool_or(v.event_type = 1 AND v.created_at < f.endings_since)
                THEN (array_agg(v.created_at ORDER BY v.created_at)
                          FILTER (WHERE v.event_type = 1 AND v.created_at >= f.endings_since))[2]
                ELSE f.endings_since END AS worker_from,
           min(v.created_at) FILTER (WHERE v.event_type <> 1) AS own_first_ending
    FROM website_event v CROSS JOIN first_ending f
    WHERE v.website_id = :website_id AND v.url_path = :path
      AND (v.event_type = 1
           OR v.event_name IN ('globe_gate', 'globe_unsupported', 'globe_error', 'globe_abandon'))
      AND v.session_id IN (SELECT session_id FROM ev)
    GROUP BY v.session_id, f.endings_since
),
measured AS (
    SELECT s.session_id,
           least(s.worker_from,
                 (SELECT max(w.created_at)
                  FROM website_event w
                  WHERE w.website_id = :website_id AND w.url_path = :path
                    AND w.event_type = 1 AND w.session_id = s.session_id
                    AND w.created_at <= s.own_first_ending)) AS measured_from
    FROM switched s
)
SELECT session_id,
       count(*) FILTER (WHERE event_type = 1)             AS views,
       count(*) FILTER (WHERE event_name = 'globe_ready') AS ready,
       coalesce(
           array_remove(
               array_agg(ms ORDER BY created_at) FILTER (WHERE event_name = 'globe_ready'),
               NULL),
           ARRAY[]::float8[]) AS ready_ms,
       count(*) FILTER (WHERE event_name = 'globe_gate' AND choice <> 'globe')  AS gate_left,
       count(*) FILTER (WHERE event_name = 'globe_abandon' AND phase = 'gate')  AS gate_quit,
       count(*) FILTER (WHERE event_name = 'globe_unsupported')                 AS unsupported,
       count(*) FILTER (WHERE event_name = 'globe_error'
                          AND (phase IS NULL
                               OR (left(phase, 3) <> 'bg:' AND phase <> 'live'))
                          AND ending IS DISTINCT FROM 'no')                     AS failed,
       count(*) FILTER (WHERE event_name = 'webgl_lost' AND phase = 'loading')  AS context_lost,
       count(*) FILTER (WHERE event_name = 'globe_abandon'
                          AND phase IS DISTINCT FROM 'gate')                    AS abandoned,
       coalesce(
           array_remove(
               array_agg(ms ORDER BY created_at) FILTER (
                   WHERE event_name = 'globe_abandon' AND phase IS DISTINCT FROM 'gate'),
               NULL),
           ARRAY[]::float8[]) AS abandon_ms
FROM ev JOIN measured m USING (session_id)
WHERE ev.created_at >= m.measured_from
GROUP BY session_id
"""

#: How many session ids have to share one path-minute before it is a machine
#: rather than a coincidence. Verified on production 2026-09-19: at three
#: there are exactly two fingerprints and no false positive; at two the result
#: is six rows and 52 sessions, because one real visitor whose browser reports
#: itself as both "safari" and "ios-webview" and one Android phone counted
#: under two operating system strings each split into two rows.
CLUSTER_MIN_IDS = 3

#: Cookieless analytics gives every request a fresh session id when the
#: client keeps no state. A headless fetcher that touches one path with three
#: ids inside the same clock minute is therefore visible as exactly that: one
#: path, one minute, several ids. Measured 2026-09-19 over seven days: 38 of
#: 163 sessions sit inside such a group, in two fingerprints - 1366x1366
#: chrome Mac OS (22) and 1280x1200 chrome Windows 10 (16). Every other
#: fingerprint peaks at one id.
#: The grouping is over EVERY event, not over page views, and that is
#: load-bearing, not an oversight: these clients fire events without ever
#: sending a page view (34 of the 163 sessions have zero page views, all of
#: them inside these two fingerprints). Adding `AND event_type = 1` was
#: proposed and measured on 2026-09-19: the maximum number of ids on one page
#: view in one minute is 2, so the query then returns ZERO rows at this
#: threshold and the detection disappears entirely. Do not add it.
#: Deliberately no path sample and no per-cluster heuristics: the output is
#: bounded to twenty fingerprint rows, and the 40-path array the first draft
#: carried was the only unbounded part of the query.
SQL_CLUSTERS = """
WITH path_minutes AS (
    SELECT url_path, date_trunc('minute', created_at) AS minute,
           array_agg(DISTINCT session_id) AS ids
    FROM website_event
    WHERE website_id = :website_id
      AND created_at >= :since AND created_at < :until
    GROUP BY 1, 2
    HAVING count(DISTINCT session_id) >= :min_ids
),
shared AS (
    SELECT DISTINCT unnest(ids) AS session_id FROM path_minutes
)
SELECT s.screen, s.browser, s.os, count(*) AS sessions
FROM shared
JOIN session s ON s.session_id = shared.session_id
GROUP BY 1, 2, 3
ORDER BY sessions DESC
LIMIT 20
"""

#: What the visitors browse with and which language their browser asks for.
#: One row per (device, language) pair, counting sessions - the panel folds
#: the two dimensions apart, because the cross product is what makes both
#: available from a single scan (four devices and eight languages live, so
#: the result is a handful of rows either way).
#: The inner DISTINCT is the window: `session` holds every session Umami ever
#: saw, so without it this would count all of history. Every session with any
#: event counts, which is the same population /overview calls `sessions.all`
#: - measured 2026-09-19 over seven days: 168 sessions.
#: `device` arrives as Umami wrote it (laptop / desktop / mobile / tablet, or
#: NULL when the client sent no screen size); the laptop-versus-desktop fold
#: belongs in pipeline/stats_analysis.py, where it can be tested and where its
#: reason is written down.
#: Deliberately no LIMIT: the panel prints a share, so the row count IS the
#: denominator, and a truncated tail would make it quietly too small. (It is
#: not the only unbounded query here - SQL_OVERVIEW, SQL_MAP, SQL_GLOBE and
#: SQL_SESSION_EVENTS carry none either, and the last of those is the one that
#: grows with traffic.) The
#: result is bounded anyway - one row per distinct (device, language) pair,
#: never more than the sessions in the window, which is four devices against
#: the handful of browser locales that reach us.
SQL_DEVICES = """
WITH seen AS (
    SELECT DISTINCT session_id
    FROM website_event
    WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
)
SELECT s.device, s.language, count(*) AS sessions
FROM seen
JOIN session s ON s.session_id = seen.session_id
GROUP BY 1, 2
ORDER BY sessions DESC
"""

#: A globe that lost its WebGL context. App sends this through
#: analytics/globeAbandon.ts reportWebglLost with `reason` (why the loop
#: stopped) and `phase`, so the panel can say whether the visitor ever saw a
#: globe at all. "loading" means before globe_ready; it is the load's one
#: ending, so it is sent at most once per load and not after another ending
#: (a globe_abandon of the same load suppresses it). "live" means after
#: globe_ready and is sent on every loss.
SQL_WEBGL_LOST = (
    """
WITH ev AS (
    SELECT
        e.event_id,
        e.session_id, e.created_at, s.country, s.device, s.browser,
        max(d.string_value) FILTER (WHERE d.data_key = 'reason') AS reason,
        max(d.string_value) FILTER (WHERE d.data_key = 'phase')  AS phase
    FROM website_event e
    JOIN event_data d ON d.website_event_id = e.event_id
    JOIN session s ON s.session_id = e.session_id
    WHERE e.website_id = :website_id AND e.event_name = 'webgl_lost'
      AND e.created_at >= :since AND e.created_at < :until
    GROUP BY e.event_id, e.session_id, e.created_at, s.country, s.device, s.browser
)
SELECT phase, reason, count(*) AS n, count(DISTINCT session_id) AS sessions,
"""
    + _LAST_VISITOR
    + """
FROM ev
WHERE phase IS NOT NULL AND reason IS NOT NULL
GROUP BY 1, 2
ORDER BY sessions DESC, n DESC
LIMIT 20
"""
)

#: What each visitor who is still here has open. One row per session: last
#: sign of life, the last page view of that session, and that page's <title>.
#: `page_title` is a plain column on website_event, filled on every page view
#: measured (2026-09-19) - a headline beats a 139-character slug and costs no
#: event_data join. The LATERAL is INNER on purpose: ten of sixty-nine
#: sessions in a day fire only `vital`/`js_error` and never a page view. They
#: have no page to name, so they have no row - the panel says so rather than
#: inventing one. The window is the 24-hour lookback; Python cuts the live
#: half out of it, so "who is here" and "who was here last" cost one query.
SQL_LIVE = """
WITH seen AS (
    SELECT session_id, max(created_at) AS last_seen
    FROM website_event
    WHERE website_id = :website_id AND created_at >= :since AND created_at < :until
    GROUP BY session_id
)
SELECT seen.session_id::text AS session,
       seen.last_seen,
       page.created_at AS page_since,
       page.url_path,
       coalesce(nullif(page.page_title, ''), page.url_path) AS title,
       s.country, s.device, s.browser
FROM seen
JOIN session s ON s.session_id = seen.session_id
JOIN LATERAL (
    SELECT e.created_at, e.url_path, e.page_title
    FROM website_event e
    WHERE e.website_id = :website_id AND e.session_id = seen.session_id
      AND e.event_type = 1
      AND e.created_at >= :since AND e.created_at < :until
    ORDER BY e.created_at DESC
    LIMIT 1
) page ON true
ORDER BY seen.last_seen DESC
LIMIT 60
"""


def fetch(sql: str, since: datetime, until: datetime, **params: Any) -> list[dict[str, Any]]:
    """Run one of the SQL_* texts for our website and the window [since, until)."""
    if not WEBSITE_ID:
        # Empty id would silently return zero rows for every panel — the
        # deploy forgot VITE_UMAMI_WEBSITE_ID in the container env.
        logger.warning("VITE_UMAMI_WEBSITE_ID is empty — every stats query returns nothing")
    with engine().connect() as conn:
        rows = conn.execute(
            text(sql), {"website_id": WEBSITE_ID, "since": since, "until": until, **params}
        )
        return [dict(r._mapping) for r in rows]

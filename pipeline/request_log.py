# SPDX-License-Identifier: AGPL-3.0-only
"""nginx's request log: every page request of every client, with its IP.

nginx writes one JSON line per page request, plus the three requests only
our JavaScript sends (``POST /api/pulse``, ``GET /pulse.js``,
``GET /api/app/interactive``), with log_format ``request`` in
ancientnerds-nginx-config to /var/www/ancientnerds/logs/requests.log,
bind-mounted read-only into the API containers at /app/logs:

    {"t":"2026-10-23T08:00:00+02:00","ip":"203.0.113.9","req":"GET /sites/peru/x-1",
     "status":200,"ua":"Mozilla/5.0 ...","ref":"https://www.google.com/","proto":"HTTP/2.0",
     "purpose":"","dest":"document","dnt":"","gpc":""}

It answers the founders dashboard's "Who is visiting?" for clients Umami
never sees: crawlers, impostors, clients without JavaScript, clients that
ignore robots.txt, and the network (AS number, pipeline/asn.py) behind each.
Every rule is pipeline/visitor_class.py's request_class(); this module reads,
groups and counts. A client is (ip, ua) on one UTC day.

nginx sees the real client address: there is no CDN in front and no
real_ip. logrotate keeps 30 days, one file per day (ops/logrotate/ancientnerds);
the panel reads the last REQUEST_DAYS. A client whose page and beacon fall
on either side of a rotation is still classed as one: the whole window is
read as one stream. One whose page and beacon fall on either side of 00:00
UTC is two clients, and its page counts without the beacon; that is about
two minutes a day, and negligible.

Never joined with a Umami session: that would need Umami's salted hash
recomputed, which de-anonymises visitors. beacon_check sets the two side by
side as aggregates only.

Stdlib only: the Lyra image ships pipeline/ without api/.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline import asn, crawler_log, log_files, referral_log, visitor_class

LOG_PATH = Path(os.getenv("REQUEST_LOG_PATH", "/app/logs/requests.log"))
#: The window the panel reports.
REQUEST_DAYS = 7
#: How many networks the panel lists per class.
TOP_ASNS = 5
#: The pages the server renders itself: the only ones whose HTML request is a
#: page view on both sides. The service worker precaches the .html SPA pages,
#: so a browser opens those without asking nginx.
SSR_PREFIXES = ("/sites/", "/articles/", "/research/", "/news-archive/")


@dataclass(frozen=True, slots=True)
class Request:
    at: datetime
    ip: str
    method: str
    path: str
    status: int
    ua: str
    ref: str
    proto: str
    purpose: str
    dest: str
    dnt: str
    gpc: str


def parse_lines(lines: Iterable[str]) -> list[Request]:
    """Every request line. A half line (nginx still writing it, or a crash)
    and broken JSON are skipped, as in crawler_log."""
    out: list[Request] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, _, target = entry["req"].partition(" ")
        out.append(
            Request(
                at=datetime.fromisoformat(entry["t"]),
                ip=entry["ip"],
                method=method,
                path=target.split("?", 1)[0],
                status=int(entry["status"]),
                ua=entry["ua"],
                ref=entry["ref"],
                proto=entry["proto"],
                purpose=entry["purpose"],
                dest=entry["dest"],
                dnt=entry["dnt"],
                gpc=entry["gpc"],
            )
        )
    return out


#: Per file of the family: its identity when parsed and what it held. A
#: rotated file never changes, so only the live one is ever parsed again.
_files: dict[Path, tuple[tuple[int, int, int], list[Request]]] = {}


def read_requests(since: datetime) -> list[Request]:
    """The requests of the family from `since` on, oldest first. The caller
    (report) has checked that the current file exists."""
    paths = [p for p in log_files.family(LOG_PATH) if not log_files.rotated_before(p, since)]
    for gone in set(_files) - set(paths):
        del _files[gone]
    for p in paths:
        identity = log_files.file_identity(p)
        if p not in _files or _files[p][0] != identity:
            _files[p] = (identity, parse_lines(log_files.read_file(p)))
    return [r for p in paths for r in _files[p][1] if r.at >= since]


def unavailable_reason() -> str:
    """Why the requests block is empty, in one English sentence for the panel."""
    return (
        f"nginx's request log is not readable at {LOG_PATH}: requests.log does not exist "
        "yet, or this is a development box. It is bind-mounted read-only into the API "
        "containers on the VPS (./logs:/app/logs:ro)."
    )


def asn_reason() -> str | None:
    """Why the report has no network columns; None when it has them."""
    return None if asn.load() is not None else asn.unavailable_reason()


def ssr_page(path: str) -> bool:
    """A path the server renders. The API counts Umami's side of beacon_check
    on the same paths."""
    return path == "/" or path.startswith(SSR_PREFIXES)


def from_search(ref: str, req: str) -> bool:
    """An arrival from a search engine, by referral_log's families; the API
    leaves the same arrivals out of Umami's side of beacon_check."""
    host = referral_log.referrer_host(ref, req)
    return bool(host) and referral_log.family_of(host) == "search"


def classify(
    requests: list[Request],
    ranges: dict[str, list[crawler_log.Network]],
    table: asn.AsnTable | None,
) -> dict[str, Any]:
    """The panel's answer for `requests`: per class its page requests and
    clients, with how many of those clients sit in a datacenter network, also
    fetched the honeypot, or are a known bot that cannot be verified; the
    top networks per class; requests per UTC day and class; and the page
    views with JavaScript on server-rendered paths for beacon_check."""
    beacons: defaultdict[tuple[date, str, str], list[datetime]] = defaultdict(list)
    trapped: set[tuple[date, str, str]] = set()
    for r in requests:
        client = (r.at.astimezone(UTC).date(), r.ip, r.ua)
        if visitor_class.is_beacon(r.method, r.path):
            beacons[client].append(r.at)
        elif visitor_class.is_honeypot(r.path) and not visitor_class.is_prefetch(r.purpose):
            trapped.add(client)
    for times in beacons.values():
        times.sort()

    requests_of: Counter[str] = Counter()
    clients_of: defaultdict[str, set[tuple[date, str, str]]] = defaultdict(set)
    unverified_of: defaultdict[str, set[tuple[date, str, str]]] = defaultdict(set)
    daily: defaultdict[str, Counter[str]] = defaultdict(Counter)
    pages_with_js = 0
    # One check per address and bot, as in crawler_log.crawler_report.
    checked: dict[tuple[str, str], bool | None] = {}
    for r in requests:
        honeypot_fetch = visitor_class.is_honeypot(r.path)
        if not (visitor_class.is_page(r.method, r.path, r.status) or honeypot_fetch):
            continue
        client = (r.at.astimezone(UTC).date(), r.ip, r.ua)
        bot = crawler_log.bot_of(r.ua)
        verified = None
        if bot is not None:
            key = (bot.operator, r.ip)
            if key not in checked:
                checked[key] = crawler_log.verified_ip(bot, r.ip, ranges)
            verified = checked[key]
        cls, unverified = visitor_class.request_class(
            purpose=r.purpose,
            ua=r.ua,
            bot_kind=None if bot is None else bot.kind,
            verified=verified,
            self_declared=bool(referral_log.BOT_UA_RE.search(r.ua)),
            honeypot=client in trapped,
            beacon=visitor_class.beacon_near(r.at, beacons.get(client, [])),
            dnt=r.dnt,
            gpc=r.gpc,
        )
        requests_of[cls] += 1
        clients_of[cls].add(client)
        if unverified:
            unverified_of[cls].add(client)
        daily[client[0].isoformat()][cls] += 1
        if (
            cls == "browser_js"
            and ssr_page(r.path)
            and not from_search(r.ref, f"{r.method} {r.path}")
        ):
            pages_with_js += 1

    networks: dict[str, tuple[int, str]] = {}
    if table is not None:
        for clients in clients_of.values():
            for _day, ip, _ua in clients:
                if ip not in networks:
                    networks[ip] = table.lookup(ip)

    classes: dict[str, dict[str, int]] = {}
    top_asns: dict[str, list[dict[str, Any]]] = {}
    for cls in visitor_class.REQUEST_CLASSES:
        clients = clients_of[cls]
        row = {
            "requests": requests_of[cls],
            "clients": len(clients),
            "honeypot": sum(1 for c in clients if c in trapped),
            "unverified": len(unverified_of[cls]),
        }
        if table is not None:
            row["datacenter"] = sum(
                1 for _d, ip, _u in clients if networks[ip][0] in asn.DATACENTER_ASNS
            )
            per_asn = Counter(networks[ip] for _d, ip, _u in clients)
            # Ties by AS number, so the list does not change between reads.
            ranked = sorted(per_asn.items(), key=lambda kv: (-kv[1], kv[0][0]))
            top_asns[cls] = [
                {"asn": number, "name": name, "clients": n}
                for (number, name), n in ranked[:TOP_ASNS]
            ]
        classes[cls] = row

    out: dict[str, Any] = {
        "covered_from": requests[0].at.astimezone(UTC).isoformat() if requests else None,
        "asn_as_of": table.as_of.isoformat() if table is not None else None,
        "classes": classes,
        "daily": [
            {"day": day, **{c: counts[c] for c in visitor_class.REQUEST_CLASSES}}
            for day, counts in sorted(daily.items())
        ],
        # The API sets umami_pageviews beside it, over the same window and paths.
        "beacon_check": {"pages_with_js": pages_with_js},
    }
    if table is not None:
        out["top_asns"] = top_asns
    return out


#: The last answer: its key, the ranges it was checked against, and itself.
_report: tuple[tuple[Any, ...], dict[str, list[crawler_log.Network]], dict[str, Any]] | None = None


def report(ranges: dict[str, list[crawler_log.Network]], now: datetime) -> dict[str, Any] | None:
    """classify() over the last REQUEST_DAYS; None while the log is missing
    (unavailable_reason says why). Loads the ASN table itself. Reused while
    no file of the family, the operators' ranges (crawler_log builds a new
    dict on every fetch, so the same object means the same lists) and the
    ASN table changed."""
    global _report
    since = now - timedelta(days=REQUEST_DAYS)
    if not LOG_PATH.exists():
        return None
    table = asn.load()
    key = (
        tuple((p, log_files.file_identity(p)) for p in log_files.family(LOG_PATH)),
        None if table is None else table.as_of,
        since.date(),
    )
    if _report is not None and _report[0] == key and _report[1] is ranges:
        return _report[2]
    out = classify(read_requests(since), ranges, table)
    _report = (key, ranges, out)
    return out

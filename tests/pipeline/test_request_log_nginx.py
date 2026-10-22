# SPDX-License-Identifier: AGPL-3.0-only
"""ancientnerds-nginx-config against pipeline/request_log.py: nginx writes
what the reader parses, for the requests the reader needs.

Ships with the nginx part of the request log and the robots.txt lines (the
second push of the visitor-classes change), not before it. The hidden anchor
that links the honeypot follows at least 48 hours later
(test_honeypot_anchor.py says why).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.robotparser import RobotFileParser

from pipeline import request_log
from pipeline import visitor_class as vc

ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / "ancientnerds-nginx-config").read_text(encoding="utf-8")


def _log_format_fields() -> list[str]:
    start = CONFIG.index("log_format request ")
    body = CONFIG[start : CONFIG.index(";", start)]
    template = "".join(re.findall(r"'([^']*)'", body))
    return list(json.loads(re.sub(r"\$\w+", "0", template)))


def _map_value(uri: str) -> str:
    """nginx's map $uri $log_request for one uri: an exact entry first, then
    the regexes in their order, then the default."""
    start = CONFIG.index("map $uri $log_request {")
    block = CONFIG[start : CONFIG.index("}", start)].splitlines()[1:]
    exact, regexes, default = {}, [], None
    for raw in block:
        key, _, value = raw.strip().rstrip(";").rpartition(" ")
        if not key:
            continue
        if key == "default":
            default = value
        elif key.startswith("~*"):
            regexes.append((re.compile(key[2:], re.IGNORECASE), value))
        elif key.startswith("~"):
            regexes.append((re.compile(key[1:]), value))
        else:
            exact[key] = value
    if uri in exact:
        return exact[uri]
    for pattern, value in regexes:
        if pattern.search(uri):
            return value
    return default


def test_the_parser_reads_exactly_the_fields_nginx_writes():
    fields = _log_format_fields()
    line = json.dumps(
        dict.fromkeys(fields, "x")
        | {"t": "2026-10-23T08:00:00+02:00", "req": "GET /", "status": 200}
    )
    (parsed,) = request_log.parse_lines([line])
    assert fields == [
        "t",
        "ip",
        "req",
        "status",
        "ua",
        "ref",
        "proto",
        "purpose",
        "dest",
        "dnt",
        "gpc",
    ]
    assert parsed.gpc == "x"


def test_the_map_keeps_pages_and_the_three_beacons():
    for uri in (
        "/",
        "/sites/peru/x-1",
        "/index-all/",
        "/pulse.js",
        "/api/pulse",
        "/api/app/interactive",
        "/map.html",
    ):
        assert _map_value(uri) == "1", uri


def test_the_map_drops_the_api_assets_and_static_files():
    for uri in (
        "/api/v1/sites",
        "/api/stats/overview",
        "/assets/index-abc.js",
        "/data/sites/index.json",
        "/fonts/x.woff2",
        "/styles.css",
        "/img/a.webp",
    ):
        assert _map_value(uri) == "0", uri


def test_the_main_server_writes_the_request_log_into_the_rotated_directory():
    assert "access_log /var/www/ancientnerds/logs/requests.log request if=$log_request;" in CONFIG
    assert request_log.LOG_PATH.name == "requests.log"


def test_the_honeypot_is_disallowed_for_first_match_parsers_and_served_404():
    # urllib.robotparser applies the first matching rule of a group, as the
    # 1994 rules do: the Disallow has to come before "Allow: /".
    robots = RobotFileParser()
    robots.parse(
        (ROOT / "ancient-nerds-map/public/robots.txt").read_text(encoding="utf-8").splitlines()
    )
    for agent in ("SomeBot/1.0", "AhrefsBot"):
        assert not robots.can_fetch(agent, f"https://ancientnerds.com{vc.HONEYPOT_PATH}"), agent
        assert robots.can_fetch(agent, "https://ancientnerds.com/sites/peru/x-1"), agent
    assert re.search(rf"location \^~ {re.escape(vc.HONEYPOT_PATH)} \{{[^}}]*return 404;", CONFIG)

# SPDX-License-Identifier: AGPL-3.0-only
"""The deploy's ASN download and its nginx step (.github/workflows/ci.yml).

pipeline/asn.py reads iptoasn.com's table from the bind mount ./asn. dockerd creates a missing
mount source as root, after which the deploy user could never write the download into it, so the
directory must exist before the first `docker compose up`. A corrupt download must abort the
deploy (set -e) before it replaces the old file. And a failed `nginx -t` must really restore the
previous config: until 2026-10-22 the step printed "Restoring previous config" and left the broken
file in sites-available.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
LINES = [line.strip() for line in CI.splitlines()]


def _first(prefix: str) -> int:
    return next(i for i, line in enumerate(LINES) if line.startswith(prefix))


def test_the_asn_directory_exists_before_any_compose_up():
    assert _first("mkdir -p asn") < _first("docker compose up")
    assert _first("mkdir -p asn") < _first(
        "BUILD_HASH=$(git rev-parse --short HEAD) docker compose up"
    )


def test_the_download_is_checked_on_its_own_line_before_it_replaces_the_file():
    test = LINES.index("gzip -t asn/ip2asn-v4-u32.tsv.gz.new")
    curl = LINES.index(
        "curl -sfRL -o asn/ip2asn-v4-u32.tsv.gz.new https://iptoasn.com/data/ip2asn-v4-u32.tsv.gz"
    )
    move = LINES.index("mv asn/ip2asn-v4-u32.tsv.gz.new asn/ip2asn-v4-u32.tsv.gz")
    assert curl < test < move
    assert LINES[curl - 1] == "if ! find asn -name ip2asn-v4-u32.tsv.gz -mtime -7 | grep -q .; then"
    # After the log streaming restart: a failed download must not stop the follow_logs restart.
    assert (
        _first("nohup ./scripts/follow_logs.sh") < curl < LINES.index('echo "==> Deploy complete!"')
    )


def test_the_asn_table_reaches_the_api_and_stays_out_of_git_and_the_image():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    api = compose[compose.index("  api: &api-service") : compose.index("  api2:")]
    assert "- ./asn:/app/asn:ro" in api
    assert "asn" in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "/asn/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_a_failed_nginx_test_restores_the_previous_config_and_fails_the_deploy():
    start = LINES.index('echo "ERROR: nginx config test failed! Restoring previous config."')
    restore = [line for line in LINES[start + 1 : start + 12] if line and not line.startswith("#")]
    assert restore[:5] == [
        "git show $BEFORE:ancientnerds-nginx-config > ancientnerds-nginx-config",
        "sudo /bin/cp /var/www/ancientnerds/ancientnerds-nginx-config "
        "/etc/nginx/sites-available/ancientnerds.com",
        "sudo /usr/sbin/nginx -t",
        "git checkout -- ancientnerds-nginx-config",
        "exit 1",
    ]


def test_the_new_deploy_lines_carry_no_apostrophe():
    """The deploy body is one single-quoted ssh argument: an apostrophe would end it."""
    start = CI.index('echo "==> Refreshing the ASN database..."')
    block = CI[CI.index("# The ASN database (pipeline/asn.py)") : CI.index("mkdir -p asn")]
    block += CI[
        CI.index("# sudo may copy only the repo file") : CI.index(
            "git checkout -- ancientnerds-nginx"
        )
    ]
    block += CI[CI.rindex("# IP-to-ASN table", 0, start) : CI.index('echo "==> Deploy complete!"')]
    assert not re.search("'", block)

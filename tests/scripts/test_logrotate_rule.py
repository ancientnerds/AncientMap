# SPDX-License-Identifier: AGPL-3.0-only
"""ops/logrotate/ancientnerds and its one-time install command (ops/logrotate/INSTALL.md).

privacy.html promises 30 days for the nginx logs with IP addresses. The rule keeps that promise
with one file per day (dateext), the live file plus 29 rotated days and ``maxage 30``; the install
command splits the logs written before the rule existed into the same per-day files. Both were
measured on 2026-10-22: the command against sampled lines of the live logs, the rule over 40
simulated days with logrotate 3.21 (the VPS's version) on Ubuntu 24.04.
"""

from __future__ import annotations

import gzip
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RULE = (ROOT / "ops" / "logrotate" / "ancientnerds").read_text(encoding="utf-8")
INSTALL = (ROOT / "ops" / "logrotate" / "INSTALL.md").read_text(encoding="utf-8")
NGINX = (ROOT / "ancientnerds-nginx-config").read_text(encoding="utf-8")
LOGS = "/var/www/ancientnerds/logs/"


def _stanzas() -> list[tuple[list[str], list[str]]]:
    """(paths, directives) of every stanza, comments stripped."""
    text = re.sub(r"#[^\n]*", "", RULE)
    out = []
    for head, body in re.findall(r"([^{}]*)\{([^{}]*)\}", text):
        directives = [" ".join(line.split()) for line in body.splitlines() if line.strip()]
        out.append((head.split(), directives))
    return out


def _stanza_of(path: str) -> list[str]:
    (directives,) = [d for paths, d in _stanzas() if path in paths]
    return directives


def test_every_nginx_log_in_the_logs_directory_is_rotated():
    logs = re.findall(r"^\s*access_log\s+(\S+)", re.sub(r"#[^\n]*", "", NGINX), re.MULTILINE)
    ours = {p for p in logs if p.startswith(LOGS)}
    assert {LOGS + "crawlers.log", LOGS + "referrals.log"} <= ours
    rotated = {p for paths, _ in _stanzas() for p in paths}
    assert ours <= rotated
    # requests.log is in the rule before nginx writes it, so it never exists unrotated.
    assert LOGS + "requests.log" in rotated


@pytest.mark.parametrize("log", ["crawlers.log", "referrals.log", "requests.log"])
def test_the_nginx_logs_keep_30_days_in_per_day_files(log):
    d = _stanza_of(LOGS + log)
    for directive in (
        "su root root",
        "daily",
        "dateext",
        "dateyesterday",
        "dateformat -%Y%m%d",
        "rotate 29",
        "maxage 30",
        "missingok",
        "compress",
        "delaycompress",
        "create 0644 www-data root",
        "postrotate",
        "invoke-rc.d nginx rotate >/dev/null 2>&1",
    ):
        assert directive in d, directive


@pytest.mark.parametrize("log", ["smtp_syn.log", "smtp_watch.log"])
def test_the_tcpdump_logs_keep_30_days_and_are_truncated_in_place(log):
    d = _stanza_of(LOGS + log)
    for directive in ("su root root", "daily", "dateext", "rotate 29", "maxage 30", "copytruncate"):
        assert directive in d, directive
    assert not any(x.startswith(("create", "postrotate")) for x in d)


def _command() -> str:
    m = re.search(
        r"<!-- install-command -->\s*```sh\n(.*?)\n```\s*<!-- /install-command -->", INSTALL, re.S
    )
    assert m, "INSTALL.md lost its marked install command"
    return m.group(1)


def test_the_install_command_installs_this_rule_and_ends_with_a_dry_run():
    cmd = _command()
    assert cmd.startswith("sudo bash -c '")  # dash has no ${d:0:4}
    assert cmd.count("'") == 2, "an apostrophe inside the command ends the quoted body"
    assert (
        "install -o root -g root -m 0644 /var/www/ancientnerds/ops/logrotate/ancientnerds /etc/logrotate.d/ancientnerds"
        in cmd
    )
    assert cmd.rstrip().endswith("logrotate -d /etc/logrotate.d/ancientnerds'")
    assert "logrotate -f" not in cmd


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX bash with GNU date and touch")
def test_the_install_command_splits_the_logs_into_29_days(tmp_path):
    """The command from INSTALL.md, run with its two paths moved into tmp_path and with
    install, chown and logrotate replaced by stubs that record their arguments."""
    www, etc, bin_ = tmp_path / "www", tmp_path / "etc", tmp_path / "bin"
    logs = www / "logs"
    (www / "ops" / "logrotate").mkdir(parents=True)
    (www / "ops" / "logrotate" / "ancientnerds").write_text(RULE, encoding="utf-8")
    logs.mkdir()
    etc.mkdir()
    bin_.mkdir()
    calls = tmp_path / "calls"
    for name, body in (
        ("install", f'echo "install $*" >> {calls}; cp "${{@: -2:1}}" "${{@: -1}}"'),
        ("chown", f'echo "chown $*" >> {calls}'),
        ("logrotate", f'echo "logrotate $*" >> {calls}'),
    ):
        (bin_ / name).write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        (bin_ / name).chmod(0o755)

    today = datetime.now().date()
    ages = [40, 30, 29, 5, 5, 1, 0, 0]

    def line(age: int, n: int) -> str:
        return f'{{"t":"{today - timedelta(days=age)}T12:00:0{n}+02:00","ip":"192.0.2.1"}}'

    for log in ("crawlers.log", "referrals.log"):
        (logs / log).write_text(
            "".join(line(a, n) + "\n" for n, a in enumerate(ages)) + '{"t":"20\n', encoding="utf-8"
        )
    (logs / "smtp_syn.log").write_text("x\n", encoding="utf-8")
    (logs / "smtp_watch.log").write_text("x\n", encoding="utf-8")
    inode = (logs / "crawlers.log").stat().st_ino

    cmd = _command().replace("/etc/logrotate.d/ancientnerds", str(etc / "ancientnerds"))
    cmd = cmd.replace("/var/www/ancientnerds", str(www)).removeprefix("sudo ")
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}
    subprocess.run(["bash", "-c", cmd], check=True, env=env, cwd=tmp_path)

    def day(age: int) -> str:
        return (today - timedelta(days=age)).strftime("%Y%m%d")

    for log in ("crawlers.log", "referrals.log"):
        names = sorted(p.name for p in logs.glob(log + "-*"))
        assert names == [f"{log}-{day(29)}.gz", f"{log}-{day(5)}.gz", f"{log}-{day(1)}"]
        assert gzip.decompress((logs / f"{log}-{day(5)}.gz").read_bytes()).decode() == (
            line(5, 3) + "\n" + line(5, 4) + "\n"
        )
        assert (logs / log).read_text(encoding="utf-8") == line(0, 6) + "\n" + line(0, 7) + "\n"
        assert not (logs / f"{log}.today").exists()
        mtime = datetime.fromtimestamp((logs / f"{log}-{day(29)}.gz").stat().st_mtime)
        assert mtime == datetime.combine(today - timedelta(days=29), datetime.min.time()).replace(
            hour=23, minute=59
        )
    assert (logs / "crawlers.log").stat().st_ino == inode, "nginx appends to the same inode"
    assert not (logs / "smtp_syn.log").exists() and not (logs / "smtp_watch.log").exists()
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert recorded[0].startswith("install -o root -g root -m 0644 ")
    assert recorded[-1] == f"logrotate -d {etc / 'ancientnerds'}"
    assert sum(r.startswith("chown www-data:root ") for r in recorded) == 6
    assert (etc / "ancientnerds").read_text(encoding="utf-8") == RULE

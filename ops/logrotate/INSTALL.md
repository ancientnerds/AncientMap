# Installing the log rotation (once, by the owner, after push 1)

`ops/logrotate/ancientnerds` rotates the nginx logs with IP addresses that the founders dashboard
reads (`crawlers.log`, `referrals.log`, `requests.log`) and the tcpdump output of the `smtp_watch`
container, daily, one file per day, kept 30 days (privacy.html section 2). The deploy cannot install
it: its sudo is limited to the nginx commands, and logrotate ignores a config that root does not
own (a symlink to the checkout would be such a config). Run this on the VPS as a user with full
sudo:

<!-- install-command -->
```sh
sudo bash -c 'set -eu
shopt -s nullglob
install -o root -g root -m 0644 /var/www/ancientnerds/ops/logrotate/ancientnerds /etc/logrotate.d/ancientnerds
cd /var/www/ancientnerds/logs
today=$(date +%Y-%m-%d)
cut=$(date -d "29 days ago" +%Y-%m-%d)
newest=$(date -d yesterday +%Y%m%d)
for f in crawlers.log referrals.log; do
  awk -v f="$f" -v today="$today" -v cut="$cut" "
    BEGIN { printf \"\" > (f \".today\") }
    { d = substr(\$0, 7, 10) }
    d >= cut && d < today { g = d; gsub(/-/, \"\", g); print > (f \"-\" g) }
    d >= today { print > (f \".today\") }" "$f"
  cat "$f.today" > "$f"
  rm "$f.today"
  for p in "$f"-2*; do
    case "$p" in *.gz) continue ;; esac
    d=${p##*-}
    touch -d "${d:0:4}-${d:4:2}-${d:6:2} 23:59" "$p"
    chown www-data:root "$p"
    [ "$d" = "$newest" ] || gzip "$p"
  done
done
rm -f smtp_syn.log smtp_watch.log
logrotate -d /etc/logrotate.d/ancientnerds'
```
<!-- /install-command -->

What it does, line by line:

- `bash`, not `sh`: Ubuntu's `sh` is dash, which has no `${d:0:4}`.
- `install` puts a root-owned copy of the rule into `/etc/logrotate.d/`. Any later edit of
  `ops/logrotate/ancientnerds` needs this `install` line again.
- The `awk` splits the existing `crawlers.log` and `referrals.log` by the date in each line's `"t"`
  field (nginx's local time, the same clock `date` reads): one file per day from 29 days ago to
  yesterday (`crawlers.log-20261021` and so on, the names `dateext` + `dateyesterday` give later
  rotations), today's lines into `<log>.today`. Older lines are not written: they are dropped.
- `cat "$f.today" > "$f"` overwrites the live file in place, so its inode, owner (www-data:root)
  and mode stay and nginx keeps appending to it. Lines nginx writes in the seconds between the
  `awk` and the `cat` are lost.
- Each day file gets the mtime 23:59 of its day (logrotate's `maxage 30` reads the mtime) and the
  owner www-data:root, then `gzip`, which keeps both. Yesterday's file stays plain, as
  `delaycompress` leaves the newest rotated file; `pipeline/log_files.py` reads both forms.
- `rm -f smtp_syn.log smtp_watch.log`: the tcpdump output of the `smtp_watch` container (exited
  since 2026-10-18, restart policy `no`). From now on the rule's second stanza keeps such files 30
  days.
- `logrotate -d` is a dry run: it changes nothing and prints what the next run would do. Paste its
  output back.

The first real rotation happens at a later run of `logrotate.timer` (daily, 00:00 local time).
There is no `logrotate -f` on purpose: a forced run on the same day would name its file after
yesterday, which the split has just written.

## Check afterwards

```sh
ls -la /var/www/ancientnerds/logs/ | grep -E "crawlers|referrals|requests|smtp"
```

- per-day `crawlers.log-YYYYMMDD.gz` and `referrals.log-YYYYMMDD.gz`, none older than 29 days,
  yesterday's plain;
- the live files `www-data root` and `-rw-r--r--`;
- no `smtp_syn.log`, no `smtp_watch.log`;
- the dashboard's "Who crawls us?" still reports, its coverage starting at most 30 days back, and
  "Where do visitors come from?" still has its history.

## Tested

2026-10-22 at 20:10 CEST, against 307 sampled lines of the live `crawlers.log` (2026-10-10 to
2026-10-22) and 387 of `referrals.log` (2026-09-17 to 2026-10-22), copied read-only. The command
was cut out of this file between the `install-command` markers.

- Git Bash (gawk), the two absolute paths pointed at a temp directory, `install`, `chown` and
  `logrotate` replaced by recording stubs: exit 0; the live files kept their inode; 12 crawler and
  29 referral day files (2026-09-23 to 2026-10-21, mtime 23:59 of their day, all `.gz` but
  2026-10-21); the day files plus the live file give back exactly the kept lines in their order
  (307 of 307 and 340 of 387: the 47 referral lines of 09-17 to 09-22 are dropped); both smtp
  files gone.
- Ubuntu 24.04 in Docker (dash as `sh`, logrotate 3.21.0 as on the VPS, TZ Europe/Berlin, the real
  `install`, `chown` and paths, the clock set with faketime): the same files, `logrotate -d` with
  no error ("log does not need rotating (log has already been rotated)" for both logs). Then 40
  daily runs at 00:00:05: the first run only records the state, the second rotates; from then on
  every log holds at most 29 day files plus the live file, the newest day file plain, the live
  file stays `www-data root 0644`, and nginx is asked to reopen once per run.
- `tests/scripts/test_logrotate_rule.py` runs the same cut-out command in CI.

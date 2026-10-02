"""Which model really wrote each recorded handoff answer (read-only census, 2026-10-01).

Every answer file carries the constant stamp OPUS_MODEL, so the stamp proves nothing. The truth is
in the Claude Code transcripts: each agent transcript names its model in every assistant message,
and its Bash commands name the `--answered-by` it recorded under. This maps answered_by -> agents
(model, active window), then classifies every answer file by the agent whose window holds its
answered_at.
"""

import collections
import json
import os
import re
import sys
from datetime import datetime

PROJ = r"C:\Users\marti\.claude\projects\C--PythonProjects-AncientMap"
HANDOFF = r"C:\PythonProjects\AncientMap\output\remediation\handoff"
OUT = r"C:\tmp\census"
BY = re.compile(r"--answered-by[ =]+['\"]?([A-Za-z0-9_.:\-]+)")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def commands(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "command" and isinstance(v, str):
                yield v
            else:
                yield from commands(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from commands(v)


DIRS = set(os.listdir(HANDOFF))
DIR_RE = re.compile(r"handoff[/\\]+([A-Za-z0-9_.\-]+)")
NAME_ANY = re.compile(r"answered[-_]by[\"']?\s*[:=,]?\s*[\"']([A-Za-z0-9_.:\-]+)")


def strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)
    elif isinstance(obj, str):
        yield obj


def scan(path):
    models = collections.Counter()
    names = set()
    dirs = set()
    first = last = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            t = rec.get("timestamp")
            if t:
                first = first or t
                last = t
            msg = rec.get("message")
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("model"):
                models[msg["model"]] += 1
                for item in msg.get("content") or []:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    for s in strings(item.get("input")):
                        if "answered" in s:
                            names.update(BY.findall(s))
                            names.update(NAME_ANY.findall(s))
                        for d in DIR_RE.findall(s):
                            if d in DIRS:
                                dirs.add(d)
    return models, names, dirs, first, last


agents = []  # (path, model, names, first, last)
for root, _, files in os.walk(PROJ):
    for f in files:
        if not f.endswith(".jsonl") or f == "journal.jsonl":
            continue
        p = os.path.join(root, f)
        models, names, dirs, first, last = scan(p)
        if not (names or dirs) or not models:
            continue
        model = models.most_common(1)[0][0]
        agents.append((p, model, names, first, last, dict(models), dirs))
by_name = collections.defaultdict(list)
by_dir = collections.defaultdict(list)
for a in agents:
    for n in a[2]:
        by_name[n].append(a)
    for d in a[6]:
        by_dir[d].append(a)


def in_window(a, at):
    return a[3] and a[4] and ts(a[3]) <= ts(at) <= ts(a[4])

counts = collections.Counter()
rows = []
for root, _, files in os.walk(HANDOFF):
    if "scratch" in root:
        continue
    for f in files:
        if not f.endswith(".answer.json"):
            continue
        p = os.path.join(root, f)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except ValueError:
            continue
        name, at = d.get("answered_by"), d.get("answered_at")
        top = os.path.relpath(root, HANDOFF).split(os.sep)[0]
        cands = by_name.get(name, [])
        hit = [a for a in cands if in_window(a, at)]
        if hit:
            how, pool = "name+window", hit
        else:
            dir_hit = [a for a in by_dir.get(top, []) if in_window(a, at)]
            if dir_hit:
                how, pool = "dir+window", dir_hit
            elif cands:
                how, pool = "name-only", cands
            else:
                how, pool = "unmapped", []
        models = sorted({a[1] for a in pool})
        true = models[0] if len(models) == 1 else ("ambiguous:" + "+".join(models) if models else "unknown")
        counts[(top, true, how)] += 1
        rows.append({"file": os.path.relpath(p, HANDOFF), "answered_by": name, "answered_at": at,
                     "stamp": d.get("model"), "true_model": true, "how": how})

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "ANSWERS_TRUE_MODEL.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
    for r in sorted(rows, key=lambda r: r["file"]):
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
summary = collections.Counter()
for (top, true, how), n in counts.items():
    summary[true] += n
print("agents with answer commands:", len(agents))
print("answers by true model:", dict(summary))
print("\nnon-opus by handoff dir (dir | model | mapping | n):")
for (top, true, how), n in sorted(counts.items()):
    if true != "claude-opus-5-5":
        print(f"  {top} | {true} | {how} | {n}")
sys.exit(0)

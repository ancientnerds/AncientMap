#!/usr/bin/env bash
# WA v3 audit k (PHASE4_V3_RUNBOOK section 7): written list, draw 10, sheets. Usage: audit_draw.sh K [EXCLUDE_FILE]
set -u
K=$1; EXCL=${2:-}
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot
export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
M=output/remediation; R4=$M/phase4_runner; P4=scripts/remediation/phase4
RUN=$R4/runs/v3-2026-09-26; L=$M/logs/p4_v3
$PY $P4/audit4.py written --run-dir $RUN --apply-root $M/logs/_write_apply_p4 > $L/written-$K.out 2>$L/written-$K.err
grep -q '^STAGE_EXIT=0' $L/written-$K.out || { echo "written failed"; tail -5 $L/written-$K.out $L/written-$K.err; exit 1; }
grep -v '^STAGE_EXIT=' $L/written-$K.out > $L/written.txt; echo "written: $(grep -c . $L/written.txt)"
X=""; [ -n "$EXCL" ] && X="--exclude $EXCL"
$PY $P4/audit4.py draw --run-dir $RUN --seed $((20260927 + K)) --count 10 --written $L/written.txt $X > $L/draw-$K.out 2>$L/draw-$K.err
grep -q '^STAGE_EXIT=0' $L/draw-$K.out || { echo "draw failed"; tail -8 $L/draw-$K.out $L/draw-$K.err; exit 1; }
grep -v '^STAGE_EXIT=' $L/draw-$K.out > $L/drawn-$K.txt; echo "drawn: $(grep -c . $L/drawn-$K.txt)"
$PY $P4/audit4.py sheet --run-dir $RUN --site-ids $L/drawn-$K.txt --out $L/AUDIT_${K}_SHEETS.md > $L/sheet-$K.out 2>&1
tail -3 $L/sheet-$K.out; ls -la $L/AUDIT_${K}_SHEETS.md

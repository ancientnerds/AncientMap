#!/usr/bin/env bash
# Lane WB write step N of run RUN (CARD_DESCRIPTIONS.md 5.4): plan, prov then card lanes, the undo
# rehearsals card then prov, accept. Stops at the first failure. Usage: wb_step.sh RUN N
set -u
RUN=$1; N=$2; NNN=$(printf %03d $N)
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
MW=scripts/remediation/mechanical/teaser.py; AP=scripts/remediation/mechanical/apply.py
D=output/remediation/mechanical_teaser/s$NNN
run() { out=$("$@" 2>&1); rc=$?; echo "$out" | grep -v "Logging configured" | tail -5; [ $rc -eq 0 ] || { echo "STOPPED rc=$rc at: $*"; exit $rc; }; }
echo "== plan step $N of $RUN"; run $PY $MW plan --run output/remediation/teaser/runs/$RUN --step $N
cells() { $PY - "$D/$1/PLAN.jsonl" <<'EOF'
import sys, os
p = sys.argv[1]
print(sum(1 for l in open(p, encoding="utf-8") if l.strip()) if os.path.exists(p) else 0)
EOF
}
for L in prov card; do
  C=$(cells $L); echo "-- lane teaser-$L-s$NNN: $C cell(s)"
  [ "$C" = "0" ] && continue
  for mode in emit rehearse probe-guards apply verify; do echo "   $mode"; run $PY $AP --lane teaser-$L-s$NNN --$mode; done
done
for L in card prov; do
  C=$(cells $L); [ "$C" = "0" ] && continue
  echo "-- rehearse-rollback teaser-$L-s$NNN"; run $PY $AP --lane teaser-$L-s$NNN --rehearse-rollback
done
echo "== accept step $N"; run $PY $MW accept --step $N
echo "STEP $N DONE"

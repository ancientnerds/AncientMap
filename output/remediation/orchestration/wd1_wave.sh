#!/usr/bin/env bash
# WD1 section 3.4: one wave W of run RUN, step by step (<=100 sites), each accepted with 0 deviations.
# Usage: wd1_wave.sh W RUN
set -u
W=$1; RUN=$2
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
F=scripts/remediation/fields; A=scripts/remediation/mechanical/apply.py
run() { out=$("$@" 2>&1); rc=$?; echo "$out" | grep -v "Logging configured" | tail -6; [ $rc -eq 0 ] || { echo "STOPPED rc=$rc at: $*"; exit $rc; }; }
if [ ! -f output/remediation/fields/wd1/write/$W/WAVE.json ]; then
  echo "== wave $W"; run $PY $F/plan.py wave --wave $W --run $RUN
fi
STEPS=$($PY -c "import json;print(len(json.load(open('output/remediation/fields/wd1/write/$W/WAVE.json',encoding='utf-8'))['steps']))")
echo "wave $W: $STEPS step(s)"
for N in $(seq 1 $STEPS); do
  S=$(printf %03d $N); L=fields-wd1-$W-s$S; D=output/remediation/fields/wd1/write/$W/s$S
  if [ -f $D/ACCEPTED.json ] || [ -f $D/NOTHING_TO_WRITE.json ]; then continue; fi
  echo "== step $N ($L)"
  run $PY $F/plan.py step --wave $W --step $N
  if [ -f $D/NOTHING_TO_WRITE.json ]; then continue; fi
  for mode in emit verify rehearse probe-guards apply verify rehearse-rollback; do
    echo "-- $mode"; run $PY $A --lane $L --$mode
  done
  echo "-- accept"; run $PY $F/plan.py accept --wave $W --step $N
done
echo "WAVE $W DONE"
$PY $F/plan.py status --wave $W 2>&1 | grep -v "Logging configured" | tail -15

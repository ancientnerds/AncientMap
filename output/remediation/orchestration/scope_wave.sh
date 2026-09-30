#!/usr/bin/env bash
# WD2 section 2.1 step 7 + gates: plan wave W of the scope review, write it through the lane gates.
# Usage: scope_wave.sh W   (W = the wave label). Exit 0 = wave landed, 20 = nothing to write, else a failed gate.
set -u
W=$1
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
SR=scripts/remediation/mechanical/scope_review.py; A=scripts/remediation/mechanical/apply.py; L=scope-review-$W
run() { out=$("$@" 2>&1); rc=$?; echo "$out" | grep -v "Logging configured" | tail -n 8; [ $rc -eq 0 ] || { echo "STOPPED rc=$rc at: $*"; exit $rc; }; }
$PY $SR export > /dev/null 2>&1 || { echo "export failed"; exit 1; }
OUT=$($PY $SR write --wave $W 2>&1); RC=$?
echo "$OUT" | grep -v "Logging configured" | tail -n 8
if echo "$OUT" | grep -qi "nothing to write"; then echo "NOTHING_TO_WRITE"; exit 20; fi
[ $RC -eq 0 ] || { echo "write failed rc=$RC"; exit $RC; }
for m in check-primitive verify interests emit rehearse probe-guards apply verify rehearse-rollback; do
  echo "-- $m"; run $PY $A --lane $L --$m
done
echo "WAVE $W LANDED"

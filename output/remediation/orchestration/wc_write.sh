#!/usr/bin/env bash
# Lane WC writes (SENTENCE_CHECK.md section 4 steps 2/4): every named WC plan, steps of <=100 sites,
# each accepted with 0 deviations before the next. Usage: wc_write.sh <plan> [<plan> ...]
set -u
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
M=output/remediation; L=$M/logs/p4wc; mkdir -p $L
PLANS=""; for p in "$@"; do PLANS="$PLANS --wc-plan $p"; done
G="$PY $M/tools/write_gate4.py --group WC"
V="$PY $M/tools/verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-%"
OUT=$($G $PLANS 2>&1); echo "$OUT" | grep -v "Logging configured" | tail -6
echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "dry run failed"; exit 1; }
OUT=$($G $PLANS --rehearse 2>&1); echo "$OUT" | grep -E "rehearsed|WRITE_EXIT" | tail -3
echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "rehearsal failed"; echo "$OUT" | tail -10; exit 1; }
N=$(ls $L | grep -c '^accept-step-.*\.log$' || true)
while true; do
  OUT=$($G $PLANS --apply --step 100 2>&1); echo "$OUT" >> $L/apply.log
  if echo "$OUT" | grep -q "no open batch left"; then echo "WC: no open batch left"; break; fi
  echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "apply failed"; echo "$OUT" | tail -12; exit 1; }
  echo "$OUT" | grep -q "STEP COMPLETE" || { echo "no step written"; echo "$OUT" | tail -12; exit 1; }
  N=$((N+1)); ACC=$L/accept-step-$(printf %02d $N).log
  $V --plan $M/logs/_write_apply_p4wc/LANE_PLAN.jsonl > $ACC 2>${ACC%.log}.err
  grep -q "ACCEPT_EXIT=0" $ACC && grep -q "RESULT: 0 deviation(s)" $ACC || { echo "acceptance $N failed"; tail -20 $ACC; exit 1; }
  A=$($G $PLANS --accept $ACC 2>&1)
  echo "$A" | grep -q "^ACCEPTED" || { echo "accept record $N failed"; echo "$A" | tail -6; exit 1; }
  echo "WC step $N: $(echo "$OUT" | grep -o 'STEP COMPLETE: [0-9]* site(s)') accepted"
done

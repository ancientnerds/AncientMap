#!/usr/bin/env bash
# Lane WA v3 writes (PHASE4_V3_RUNBOOK.md section 7): steps of <=100 sites, each accepted before the
# next. Stops at the first failure, and with exit 10 when the next 500-site audit is due.
set -u
cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot
export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
M=output/remediation; R4=$M/phase4_runner; P4=scripts/remediation/phase4
RUNNAME=v3-2026-09-26; RUN=$R4/runs/$RUNNAME; L=$M/logs/p4_v3; mkdir -p $L
ROUNDS="--plan $R4/PLAN4.v3.jsonl --run-dir $RUN --log-dir $L --searches-off"
RUNS="--run $R4/runs/pilot4-2026-09-24 --run $R4/runs/mass-2026-09-25 --run $R4/runs/d9-2026-09-25 --run $R4/runs/v3-2026-09-26 --run $R4/runs/v3d-2026-09-26"
ALLOW="--allow-stamp phase4l:% --allow-stamp wb-teaser-prov-% --allow-stamp phase4wc:%"
AUDIT_EVERY=500
B=$($PY $P4/mass4.py $ROUNDS 2>/dev/null | sed -n 's/^done *//p' | sed 's/,/ --batch /g; s/^/--batch /')
[ -n "$B" ] || { echo "no done batch"; exit 1; }
G4="$PY $M/tools/write_gate4.py --group P4 --run $RUNNAME --open-lanes W,S"
written() { $PY $P4/audit4.py written --run-dir $RUN --apply-root $M/logs/_write_apply_p4 2>/dev/null | grep -v '^STAGE_EXIT=' | grep -c .; }
AUDITED=$(cat $L/audited_upto 2>/dev/null || echo 0)
N=$(ls $L | grep -c '^accept-step-' || true)
if [ ! -f $L/rehearsed.ok ]; then
  OUT=$($G4 $B 2>&1); echo "$OUT" > $L/dry.log
  echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "dry run failed"; echo "$OUT" | tail -15; exit 1; }
  echo "$OUT" | grep -E "defect scope|descriptions-only|rows planned|refused by rule" | head -8
  OUT=$($G4 $B --rehearse 2>&1); echo "$OUT" > $L/rehearse.log
  echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "rehearsal failed"; echo "$OUT" | tail -15; exit 1; }
  touch $L/rehearsed.ok; echo "rehearsal: every open batch rehearsed"
fi
while true; do
  W=$(written)
  if [ $((W - AUDITED)) -ge $AUDIT_EVERY ]; then echo "AUDIT_DUE written=$W audited_upto=$AUDITED"; exit 10; fi
  OUT=$($G4 $B --apply --step 100 2>&1); echo "$OUT" >> $L/apply.log
  if echo "$OUT" | grep -q "no open batch left"; then echo "P4 v3: all batches written (written=$W)"; break; fi
  echo "$OUT" | grep -q "WRITE_EXIT=0" || { echo "apply failed"; echo "$OUT" | tail -12; exit 1; }
  echo "$OUT" | grep -q "STEP COMPLETE" || { echo "no step written"; echo "$OUT" | tail -12; exit 1; }
  N=$((N+1)); ACC=$L/accept-step-$(printf %02d $N).log
  $PY $M/tools/verify_writes4.py --lane p4 --plan $M/logs/_write_apply_p4/LANE_PLAN.jsonl $RUNS $ALLOW > $ACC 2>${ACC%.log}.err
  grep -q "ACCEPT_EXIT=0" $ACC && grep -q "RESULT: 0 deviation(s)" $ACC || { echo "acceptance $N failed"; tail -25 $ACC; exit 1; }
  A=$($G4 --accept $ACC 2>&1)
  echo "$A" | grep -q "^ACCEPTED" || { echo "accept record $N failed"; echo "$A" | tail -6; exit 1; }
  echo "step $N: $(echo "$OUT" | grep -o 'STEP COMPLETE: [0-9]* site(s)') accepted"
done

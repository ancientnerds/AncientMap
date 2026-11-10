#!/usr/bin/env bash
# WD5 (docs/procedures/FIELDS_WD5.md section 6): one wave W of run RUN, step by step (<=100 sites), each
# accepted with 0 deviations. Like output/remediation/orchestration/wd3_wave.sh, for the `recheck`
# rule (stage wd5) and the dating extractor's `extract` rule (stage wd5x, FIELDS_WD5.md section 14):
# the lanes are fields-$STAGE-W-sNNN, the steps live under output/remediation/fields/$STAGE/write/W,
# and every plan.py command but `wave` (which reads the stage from RUN's RUN.json) takes --stage $STAGE.
# `plan.py wave` refuses a wd5 run whose adversarial re-check is not applied (adversarial.py apply), and
# a wd5x run without a passing sealed gold verdict, VERIFIED.json and OWNER_SHOWN.json.
# Usage: wd5_wave.sh W RUN [STAGE]   STAGE wd5 (the default, as before) or wd5x
#   e.g. wd5_wave.sh 2026-10-12b output/remediation/fields/wd5
#        wd5_wave.sh 2026-11-10 output/remediation/fields/wd5x wd5x
set -u
W=$1; RUN=$2; STAGE=${3:-wd5}
case "$STAGE" in
  wd5|wd5x) ;;
  *) echo "STOPPED: stage $STAGE is not wd5 or wd5x"; exit 2 ;;
esac
cd "$(git rev-parse --show-toplevel)"
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
F=scripts/remediation/fields; A=scripts/remediation/mechanical/apply.py
WAVES=output/remediation/fields/$STAGE/write
run() { out=$("$@" 2>&1); rc=$?; echo "$out" | grep -v "Logging configured" | tail -6; [ $rc -eq 0 ] || { echo "STOPPED rc=$rc at: $*"; exit $rc; }; }
RULE_STAGE=$($PY -c "import json,sys;print(json.load(open(sys.argv[1]+'/RUN.json',encoding='utf-8'))['stage'])" "$RUN")
if [ "$RULE_STAGE" != "$STAGE" ]; then
  echo "STOPPED: $RUN is a $RULE_STAGE run, not $STAGE"; exit 2
fi
if [ ! -f $WAVES/$W/WAVE.json ]; then
  echo "== wave $W"; run $PY $F/plan.py wave --wave $W --run $RUN
fi
STEPS=$($PY -c "import json;print(len(json.load(open('$WAVES/$W/WAVE.json',encoding='utf-8'))['steps']))")
echo "wave $W: $STEPS step(s)"
for N in $(seq 1 $STEPS); do
  S=$(printf %03d $N); L=fields-$STAGE-$W-s$S; D=$WAVES/$W/s$S
  if [ -f $D/ACCEPTED.json ]; then continue; fi
  echo "== step $N ($L)"
  run $PY $F/plan.py step --stage $STAGE --wave $W --step $N
  if [ -f $D/NOTHING_TO_WRITE.json ]; then   # every cell refused: accept the empty step, the next one needs it
    echo "-- nothing to write"; run $PY $F/plan.py accept --stage $STAGE --wave $W --step $N; continue
  fi
  for mode in emit verify rehearse probe-guards apply verify rehearse-rollback; do
    echo "-- $mode"; run $PY $A --lane $L --$mode
  done
  echo "-- accept"; run $PY $F/plan.py accept --stage $STAGE --wave $W --step $N
done
echo "WAVE $W DONE"
$PY $F/plan.py status --stage $STAGE --wave $W 2>&1 | grep -v "Logging configured" | tail -15

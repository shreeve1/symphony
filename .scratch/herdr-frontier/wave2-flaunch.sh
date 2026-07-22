#!/usr/bin/env bash
# wave2 (F-series #33/#34/#35) launch — James's proven config from the #31/#32 run.
set -uo pipefail
export HERDR_ENV=1
export HERDR_ORCH_WORKER_SKILLS="$HOME/.claude/skills/implement"
export HERDR_ORCH_EXTENSIONS="$HOME/.pi/agent/extensions/pi-duo" # makes pi-duo/Duo available
export HERDR_ORCH_WORKER_MODELS="pi-duo/Duo,deepseek/deepseek-v4-flash"
export HERDR_ORCH_REVIEWER_MODELS="deepseek/deepseek-v4-flash,minimax/MiniMax-M3"
export HERDR_ORCH_WAIT_MS="${HERDR_ORCH_WAIT_MS:-2700000}" # 45-min per-cycle budget

STATE_DIR=/tmp/herdr-frontier-wave2-NxjN
SKILL_DIR=/home/james/.pi/agent/skills/herdr-issue-frontier
echo "=== wave2 #33/#34/#35 (worker=pi-duo/Duo; F-series w/ prototype ref) launch $(date) ===" >>"$STATE_DIR/wave.log"
bash "$SKILL_DIR/scripts/wave.sh" "$STATE_DIR/wave.manifest" "$STATE_DIR" 2>&1 | tee -a "$STATE_DIR/wave.log"
rc=${PIPESTATUS[0]}
echo "=== WAVE2_DONE rc=$rc at $(date) ===" >>"$STATE_DIR/wave.log"

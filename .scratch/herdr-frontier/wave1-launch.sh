#!/usr/bin/env bash
# Launch herdr-issue-frontier wave 1 (parentless: #30,#31,#32). Background-safe.
set -uo pipefail
export HERDR_ENV=1
export HERDR_ORCH_WORKER_SKILLS="$HOME/.claude/skills/implement" # only implement loads; discovery off
export HERDR_ORCH_WAIT_MS="${HERDR_ORCH_WAIT_MS:-1800000}"       # 30-min per-cycle budget (frontier default)
# Model tiers bridged from models.conf (probing fallback; primitive reads HERDR_ORCH_*_MODELS)
export HERDR_ORCH_WORKER_MODELS="minimax/MiniMax-M3,deepseek/deepseek-v4-flash"
export HERDR_ORCH_REVIEWER_MODELS="deepseek/deepseek-v4-flash,minimax/MiniMax-M3"

STATE_DIR=/tmp/herdr-frontier-yPhn
SKILL_DIR=/home/james/.pi/agent/skills/herdr-issue-frontier

echo "=== wave 1 launch $(date) ===" >>"$STATE_DIR/wave.log"
bash "$SKILL_DIR/scripts/wave.sh" "$STATE_DIR/wave.manifest" "$STATE_DIR" 2>&1 | tee -a "$STATE_DIR/wave.log"
rc=${PIPESTATUS[0]}
echo "=== WAVE_DONE rc=$rc at $(date) ===" >>"$STATE_DIR/wave.log"

#!/usr/bin/env bash
# wave2-launch.sh — issues #31 + #32 (2-way) through the FIXED primitive.
# Proven config from the #30 canary: worker pi-duo/Duo (+ pi-duo extension),
# status-gated waits, --no-context-files, 45-min per-turn budget.
set -uo pipefail
export HERDR_ENV=1
export HERDR_ORCH_WORKER_SKILLS="$HOME/.claude/skills/implement"
export HERDR_ORCH_EXTENSIONS="$HOME/.pi/agent/extensions/pi-duo"
export HERDR_ORCH_WORKER_MODELS="pi-duo/Duo,deepseek/deepseek-v4-flash"
export HERDR_ORCH_REVIEWER_MODELS="deepseek/deepseek-v4-flash,minimax/MiniMax-M3"
export HERDR_ORCH_WAIT_MS="${HERDR_ORCH_WAIT_MS:-2700000}"          # 45-min per-cycle budget
STATE=/tmp/herdr-frontier-wave2
SKILL=/home/james/.pi/agent/skills/herdr-issue-frontier
echo "=== wave2 #31/#32 (worker=pi-duo/Duo) launch $(date) ===" >>"$STATE/wave.log"
bash "$SKILL/scripts/wave.sh" "$STATE/wave.manifest" "$STATE" 2>&1 | tee -a "$STATE/wave.log"
rc=${PIPESTATUS[0]}
echo "=== WAVE2_DONE rc=$rc at $(date) ===" >>"$STATE/wave.log"

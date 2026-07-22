#!/usr/bin/env bash
# canary-launch.sh — ONE issue (#30) through the FIXED primitive, worker model
# pi-duo/Duo (extension-provided, so HERDR_ORCH_EXTENSIONS loads it for both the
# probe and the pane). 45-min per-turn budget (minimax ran >30; bumped per trap #3).
set -uo pipefail
export HERDR_ENV=1
export HERDR_ORCH_WORKER_SKILLS="$HOME/.claude/skills/implement"
export HERDR_ORCH_EXTENSIONS="$HOME/.pi/agent/extensions/pi-duo"   # registers pi-duo/Duo
export HERDR_ORCH_WORKER_MODELS="pi-duo/Duo,deepseek/deepseek-v4-flash"   # Duo primary, deepseek fallback
export HERDR_ORCH_REVIEWER_MODELS="deepseek/deepseek-v4-flash,minimax/MiniMax-M3"
export HERDR_ORCH_WAIT_MS="${HERDR_ORCH_WAIT_MS:-2700000}"          # 45-min per-cycle budget
STATE=/tmp/herdr-frontier-canary30
SKILL=/home/james/.pi/agent/skills/herdr-issue-frontier
echo "=== canary #30 (worker=pi-duo/Duo) launch $(date) ===" >>"$STATE/wave.log"
bash "$SKILL/scripts/wave.sh" "$STATE/wave.manifest" "$STATE" 2>&1 | tee -a "$STATE/wave.log"
rc=${PIPESTATUS[0]}
echo "=== CANARY_DONE rc=$rc at $(date) ===" >>"$STATE/wave.log"

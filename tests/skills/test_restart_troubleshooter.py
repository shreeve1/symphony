from __future__ import annotations

import os
import subprocess
from pathlib import Path

RESTART_PATH = Path(".claude/skills/symphony-restart/SKILL.md")
TROUBLESHOOTER_PATH = Path(".claude/skills/symphony-troubleshooter/SKILL.md")
DEPLOY_PATH = Path("web/frontend/deploy.sh")


def test_restart_skill_is_repo_local_and_keeps_approval_gate() -> None:
    text = RESTART_PATH.read_text(encoding="utf-8")

    assert "name: symphony-restart" in text
    assert "symphony-host.service" in text
    assert "explicit James approval" in text
    assert "--full-stack" in text
    assert "podium-migrations.service" in text
    assert "podium-api.service" in text
    assert "podium-web.service" in text
    assert "web/frontend/deploy.sh" in text
    assert "/api/health" in text
    assert "symphony_started" in text
    assert "reconcile_startup_" in text
    assert "dispatch_completed" in text
    assert "/home/james/symphony-host.env" in text
    assert "Never read or print" in text
    assert (
        "Podium operations require `--full-stack`, `full rebuild`, or an explicit request to rebuild/restart Podium"
        in text
    )
    assert "A read-only request that merely mentions Podium is not approval" in text
    assert "API_STATUS" in text
    assert '[ "$API_STATUS" = 200 ]' in text
    assert "<recorded MainPID>" in text
    assert "reconcile_startup_failed|run_reconcile_failed|pi_rpc_probe_failed" in text

    full_stack = text.index("### 4. Rebuild and restart Podium")
    scheduler = text.index("### 5. Scheduler restart decision")
    assert text.index("explicit James approval") < full_stack
    for command in [
        "\nsudo systemctl restart podium-migrations.service\n",
        "\nsudo systemctl restart podium-api.service\n",
        "\nweb/frontend/deploy.sh\n",
    ]:
        assert text.count(command) == 1
        assert full_stack < text.index(command) < scheduler


def test_frontend_deploy_busts_cache_and_requires_http_200() -> None:
    text = DEPLOY_PATH.read_text(encoding="utf-8")

    assert "git diff --quiet HEAD -- tsconfig.json" in text
    assert "rm -rf .next/cache" in text
    assert "curl -fsS" in text
    assert '[ "$STATUS" = 200 ]' in text
    assert "trap 'git checkout -- tsconfig.json' EXIT" in text
    assert "git checkout -- tsconfig.json" in text
    assert "trap - EXIT" in text
    assert "for _ in {1..20}" in text
    assert '[[ "$STATE" != inactive && "$STATE" != failed ]]' in text
    assert "restarting the untouched current build" in text
    assert 'sudo systemctl restart "$SERVICE"' in text
    assert "git checkout -- tsconfig.json 2>/dev/null || true" not in text


def test_frontend_deploy_orders_build_wait_swap_and_start(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    deploy = frontend / "deploy.sh"
    deploy.write_text(DEPLOY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    deploy.chmod(0o755)
    (frontend / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (frontend / ".next").mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "commands.log"
    state = tmp_path / "service.state"
    count = tmp_path / "poll.count"

    def fake(name: str, body: str) -> None:
        path = fake_bin / name
        path.write_text(
            f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n", encoding="utf-8"
        )
        path.chmod(0o755)

    fake("git", 'echo "git $*" >> "$LOG"')
    fake("rm", 'echo "rm $*" >> "$LOG"; /bin/rm "$@"')
    fake("mv", 'echo "mv $*" >> "$LOG"; /bin/mv "$@"')
    fake("pnpm", 'echo "pnpm $*" >> "$LOG"; mkdir -p "$NEXT_DIST_DIR"')
    fake("sleep", 'echo "sleep $*" >> "$LOG"')
    fake("sudo", 'echo "sudo $*" >> "$LOG"; "$@"')
    fake(
        "systemctl",
        """
        echo "systemctl $*" >> "$LOG"
        case "$1" in
          stop)
            if [[ "$STOP_FAIL" == 1 ]]; then
              echo active > "$STATE_FILE"
              exit 1
            fi
            echo deactivating > "$STATE_FILE"
            echo 0 > "$COUNT_FILE"
            ;;
          start|restart) echo active > "$STATE_FILE" ;;
          is-active)
            current="$(cat "$STATE_FILE")"
            if [[ "$current" == deactivating ]]; then
              polls="$(( $(cat "$COUNT_FILE") + 1 ))"
              echo "$polls" > "$COUNT_FILE"
              if (( polls >= SETTLE_AFTER )); then
                current=inactive
                echo inactive > "$STATE_FILE"
              fi
            fi
            echo "$current"
            [[ "$current" == active ]]
            ;;
        esac
        """,
    )
    fake("curl", 'echo "curl $*" >> "$LOG"; printf 200')

    result = subprocess.run(
        [str(deploy)],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "LOG": str(log),
            "STATE_FILE": str(state),
            "COUNT_FILE": str(count),
            "SETTLE_AFTER": "2",
            "STOP_FAIL": "0",
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr

    lines = log.read_text(encoding="utf-8").splitlines()
    cursor = -1
    for expected in [
        "rm -rf .next/cache .next.staging",
        "pnpm build",
        "sudo systemctl stop podium-web.service",
        "systemctl is-active podium-web.service",
        "systemctl is-active podium-web.service",
        "mv .next .next.prev",
        "mv .next.staging .next",
        "sudo systemctl start podium-web.service",
        "curl -fsS",
    ]:
        cursor = next(
            index
            for index, line in enumerate(lines[cursor + 1 :], cursor + 1)
            if expected in line
        )

    log.write_text("", encoding="utf-8")
    result = subprocess.run(
        [str(deploy)],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "LOG": str(log),
            "STATE_FILE": str(state),
            "COUNT_FILE": str(count),
            "SETTLE_AFTER": "21",
            "STOP_FAIL": "0",
        },
        check=False,
    )
    assert result.returncode != 0
    timeout_lines = log.read_text(encoding="utf-8").splitlines()
    assert "sudo systemctl restart podium-web.service" in timeout_lines
    assert "mv .next .next.prev" not in timeout_lines

    log.write_text("", encoding="utf-8")
    result = subprocess.run(
        [str(deploy)],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "LOG": str(log),
            "STATE_FILE": str(state),
            "COUNT_FILE": str(count),
            "SETTLE_AFTER": "2",
            "STOP_FAIL": "1",
        },
        check=False,
    )
    assert result.returncode != 0
    stop_failure_lines = log.read_text(encoding="utf-8").splitlines()
    assert "sudo systemctl restart podium-web.service" in stop_failure_lines
    assert "mv .next .next.prev" not in stop_failure_lines


def test_troubleshooter_skill_is_podium_era_and_read_only() -> None:
    text = TROUBLESHOOTER_PATH.read_text(encoding="utf-8")

    assert "name: symphony-troubleshooter" in text
    assert "Podium" in text
    assert "GET /api/bindings" in text
    assert "GET /api/issues/{issue_id}/runs" in text
    assert "GET /api/runs/{run_id}" in text
    assert "/api/bindings/$NAME/issues" in text
    assert "sqlite3" in text
    assert "symphony-binding-scaffold" in text
    assert "symphony-binding-smoke" in text
    # symphony-workflow-author retired (ADR-0016) — no longer referenced.
    assert "symphony-plane-recover" in text
    assert "read-only" in text.lower()
    assert "Never read or print" in text


def test_repo_local_operational_skills_do_not_keep_stale_plane_scaffold_language() -> (
    None
):
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in [RESTART_PATH, TROUBLESHOOTER_PATH]
    )

    assert "/home/james/plane" not in combined
    assert "symphony-project-scaffold" not in combined
    assert "Plane ticket" not in combined
    assert "Plane write" not in combined
    assert "api/v1/workspaces" not in combined

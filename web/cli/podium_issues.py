"""Create Podium issues from an LLM-sliced plan spec.

The /podium-issues skill does the natural-language slicing. This module resolves
the Podium binding for cwd, then inserts the already-sliced issues in dependency
order so blocked_by contains real Podium ids. Slicer-created issues are auto-land
eligible because each slice is required to carry a runnable verification command.

Each slice may optionally pin a `model` and `agent`. When a model is set the
slice is validated against `models.yml` at load time with the same resolver
dispatch uses (model_catalog.resolve_model + an agent-match assertion), so
authoring and dispatch share one contract -- a typo'd model fails here instead
of writing an auto_land issue that silently stalls a dependent batch at dispatch.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

from model_catalog import KNOWN_AGENTS, ModelResolutionError, load_models, resolve_model

_db = cast(Any, import_module("web.api.db"))
_seed = cast(Any, import_module("web.api.seed"))
connect = _db.connect
BINDINGS_PATH = _seed.BINDINGS_PATH


class PodiumIssuesError(RuntimeError):
    """Raised for operator-facing failures."""


@dataclass(frozen=True)
class PlanSlice:
    key: str
    title: str
    description: str
    acceptance: list[str]
    verification: str
    blocked_by: list[str]
    locks: list[str]
    priority: int | None = None
    model: str | None = None
    agent: str | None = None


def _git_toplevel(cwd: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return cwd.resolve()


def resolve_binding_for_cwd(
    cwd: Path, bindings_path: Path = BINDINGS_PATH
) -> dict[str, Any]:
    root = _git_toplevel(cwd)
    bindings = _seed._load_bindings(bindings_path)
    podium = [b for b in bindings if str(b.get("tracker")) == "podium"]
    for binding in podium:
        repo_path = binding.get("repo_path")
        if repo_path and Path(repo_path).resolve() == root:
            return binding
    names = ", ".join(sorted(str(b["name"]) for b in podium)) or "(none)"
    raise PodiumIssuesError(
        f"no podium binding matches {root}; available podium bindings: {names}"
    )


def _load_plan_slices(plan_path: Path) -> list[PlanSlice]:
    raw = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    rows = raw.get("slices") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise PodiumIssuesError(f"{plan_path}: expected non-empty 'slices' list")

    slices: list[PlanSlice] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise PodiumIssuesError(f"{plan_path}: slice {idx} is not an object")
        key = str(row.get("key") or idx)
        if key in seen:
            raise PodiumIssuesError(f"{plan_path}: duplicate slice key {key!r}")
        seen.add(key)
        title = str(row.get("title") or "").strip()
        verification = str(row.get("verification") or "").strip()
        if not title or not verification:
            raise PodiumIssuesError(
                f"{plan_path}: slice {key!r} needs title+verification"
            )
        acceptance = [str(x) for x in row.get("acceptance", [])]
        if not acceptance:
            raise PodiumIssuesError(f"{plan_path}: slice {key!r} needs acceptance")
        model = row.get("model")
        agent = row.get("agent")
        if model is not None:
            model = str(model).strip()
            if not model:
                raise PodiumIssuesError(
                    f"{plan_path}: slice {key!r} model must not be empty"
                )
        if agent is not None:
            agent = str(agent).strip()
            if not agent:
                raise PodiumIssuesError(
                    f"{plan_path}: slice {key!r} agent must not be empty"
                )
            if agent not in KNOWN_AGENTS:
                raise PodiumIssuesError(
                    f"{plan_path}: slice {key!r} agent {agent!r} "
                    f"must be one of {KNOWN_AGENTS}"
                )
        slices.append(
            PlanSlice(
                key=key,
                title=title,
                description=str(row.get("description") or "").strip(),
                acceptance=acceptance,
                verification=verification,
                blocked_by=[str(x) for x in row.get("blocked_by", [])],
                locks=[str(x) for x in row.get("locks", [])],
                priority=row.get("priority"),
                model=model,
                agent=agent,
            )
        )
    unknown = sorted({b for s in slices for b in s.blocked_by} - seen)
    if unknown:
        raise PodiumIssuesError(f"{plan_path}: unknown blocked_by keys: {unknown}")
    return _dependency_order(slices)


def _dependency_order(slices: list[PlanSlice]) -> list[PlanSlice]:
    remaining = {s.key: s for s in slices}
    emitted: set[str] = set()
    ordered: list[PlanSlice] = []
    while remaining:
        ready = [
            s
            for s in slices
            if s.key in remaining and all(b in emitted for b in s.blocked_by)
        ]
        if not ready:
            raise PodiumIssuesError("slice dependency cycle detected")
        for item in ready:
            ordered.append(item)
            emitted.add(item.key)
            remaining.pop(item.key)
    return ordered


def _validate_model_agent(
    slices: list[PlanSlice], default_agent: str, models: list[dict[str, Any]]
) -> None:
    """Validate each slice's model against models.yml the way dispatch will.

    Mirrors the model/agent portion of scheduler `_apply_dispatch_gate`:
    resolve_model alone can return a single match whose agent differs from the
    requested one (its `len(matches) == 1` branch), so the agent-match assertion
    is mandatory -- exactly the check dispatch performs.
    """
    for slice_ in slices:
        if slice_.model is None:
            continue
        agent = slice_.agent or default_agent
        try:
            entry = resolve_model(slice_.model, models, agent=agent)
        except ModelResolutionError as exc:
            raise PodiumIssuesError(
                f"slice {slice_.key!r}: model {slice_.model!r}: {exc}"
            ) from exc
        if entry["agent"] != agent:
            raise PodiumIssuesError(
                f"slice {slice_.key!r}: model {slice_.model!r} requires agent "
                f"{entry['agent']!r} but resolves to agent {agent!r}; "
                "set agent: to match"
            )


def _description(slice_: PlanSlice) -> str:
    acceptance = "\n".join(f"- [ ] {item}" for item in slice_.acceptance)
    return (
        f"## What to build\n\n{slice_.description}\n\n"
        f"## Acceptance criteria\n\n{acceptance}\n\n"
        f"## Verification\n\n{slice_.verification}\n"
    )


def _insert_issue(
    connection: sqlite3.Connection,
    binding: dict[str, Any],
    slice_: PlanSlice,
    blocked_by_ids: list[int],
    now: str,
) -> int:
    approval = binding.get("approval") or {}
    approval_required = (
        bool(approval.get("enabled")) if isinstance(approval, dict) else False
    )
    worktree_default = binding.get("worktree_default")
    if worktree_default is None:
        worktree_default = binding.get("type", "infra") == "coding"
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          approval_required, approved, auto_land, scheduled_for, base_branch, comments_md,
          context_md, external_id, blocked_by, locks, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', ?, ?, ?, NULL, 'high', ?, ?, 0, 1, NULL, ?, '', '', NULL, ?, ?, ?, ?)
        """,
        (
            str(binding["name"]),
            slice_.title,
            _description(slice_),
            slice_.priority,
            slice_.agent or str(binding.get("default_agent") or "pi"),
            slice_.model,
            int(bool(worktree_default)),
            int(approval_required),
            str(binding.get("base_branch") or "main"),
            json.dumps(blocked_by_ids),
            json.dumps(slice_.locks),
            now,
            now,
        ),
    )
    issue_id = cursor.lastrowid
    if issue_id is None:
        raise RuntimeError("insert did not return an issue id")
    return int(issue_id)


def create_plan_issues(
    cwd: Path,
    plan_path: Path,
    *,
    bindings_path: Path = BINDINGS_PATH,
    dry_run: bool = False,
) -> list[str]:
    binding = resolve_binding_for_cwd(cwd, bindings_path)
    slices = _load_plan_slices(plan_path)
    name = str(binding["name"])
    default_agent = str(binding.get("default_agent") or "pi")
    if any(s.model for s in slices):
        try:
            models = load_models()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise PodiumIssuesError(f"could not read models.yml: {exc}") from exc
        _validate_model_agent(slices, default_agent, models)
    lines = [f"binding={name} slices={len(slices)}"]
    if dry_run:
        for slice_ in slices:
            deps = ",".join(slice_.blocked_by) or "none"
            locks = ",".join(slice_.locks) or "none"
            suffix = ""
            if slice_.model:
                suffix += f" model={slice_.model}"
            if slice_.agent:
                suffix += f" agent={slice_.agent}"
            lines.append(
                f"{slice_.key} '{slice_.title}' blocked_by={deps} locks={locks}{suffix} -> podium (dry-run)"
            )
        return lines

    created: dict[str, int] = {}
    now = datetime.now(UTC).isoformat()
    connection = connect()
    try:
        for slice_ in slices:
            blocked_by_ids = [created[key] for key in slice_.blocked_by]
            issue_id = _insert_issue(connection, binding, slice_, blocked_by_ids, now)
            created[slice_.key] = issue_id
            connection.commit()
            lines.append(f"{slice_.key} '{slice_.title}' -> podium #{issue_id}")
    finally:
        connection.close()
    return lines


def list_issues(binding_name: str | None = None) -> list[str]:
    connection = connect()
    try:
        if binding_name:
            rows = connection.execute(
                """
                SELECT id, binding_name, title, state, blocked_by, locks, auto_land
                FROM issue WHERE binding_name = ? ORDER BY id
                """,
                (binding_name,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, binding_name, title, state, blocked_by, locks, auto_land
                FROM issue ORDER BY id
                """
            ).fetchall()
    finally:
        connection.close()
    lines = []
    for row in rows:
        blocked_by = json.loads(row[4] or "[]")
        locks = json.loads(row[5] or "[]")
        lines.append(
            f"#{row[0]} {row[1]} {row[3]} auto_land={bool(row[6])} blocked_by={blocked_by} locks={locks} {row[2]}"
        )
    return lines or ["no issues"]


# --- sync_from_github (ADR-0042 section 1) ---
# GitHub is the human-visible issue surface; Podium is the private execution
# mirror the scheduler dispatches from. This helper mirrors open, ready-for-agent
# GitHub child issues (those carrying a `## Parent` heading) into Podium as new
# `todo` rows, deduped on the UNIQUE `external_id` index. Insert-only: a row that
# already exists is left untouched (no title/body/state overwrite), so re-running
# sync is always safe mid-flight. `auto_land` is decided at insert time on whether
# `_extract_runnable_verification` extracts a runnable `## Verification` command
# from the body, mirroring ADR-0023's explicit-`auto_land` invariant.

_ISSUE_REF = re.compile(r"(?:[\w.-]+/[\w.-]+)?#(\d+)")


def _extract_runnable_verification(body: str) -> str:
    """Wrapper around scheduler._extract_runnable_verification (lazy import)."""
    _scheduler = cast(Any, import_module("scheduler"))
    return _scheduler._extract_runnable_verification(body)


def _has_parent_section(body: str) -> bool:
    """Return True if the body has a non-empty `## Parent` section.

    A child issue linked to a parent spec carries a `## Parent` heading with at
    least one ``#<digits>`` reference in the section body. A bare
    `## Parent\\n\\nNone` section (the no-parent marker some templates emit) is
    treated as no parent.
    """
    heading = re.search(r"^##[ \t]+Parent[ \t]*$", body, re.MULTILINE)
    if heading is None:
        return False
    next_heading = re.search(r"^##[ \t]+", body[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(body)
    section = body[heading.end() : end]
    return bool(_ISSUE_REF.search(section))


def _extract_blocked_by_numbers(body: str) -> list[int]:
    """Parse the `## Blocked by` section for `#N` references.

    Returns the referenced issue numbers in document order, deduplicated. Lines
    like `None — can start immediately.` (the to-tickets no-blocker marker) and
    prose that mentions `#N` without a `## Blocked by` heading are ignored.
    """
    heading = re.search(r"^##[ \t]+Blocked[ \t]+by[ \t]*$", body, re.MULTILINE)
    if heading is None:
        return []
    next_heading = re.search(r"^##[ \t]+", body[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(body)
    section = body[heading.end() : end]
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _ISSUE_REF.finditer(section):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        ordered.append(number)
    return ordered


def _run_gh_issue_list(owner: str, repo: str) -> list[dict[str, Any]]:
    """Invoke `gh issue list` and parse its JSON output.

    Returned shape per element: ``{number, title, body, labels}``. A `gh` failure
    surfaces as ``PodiumIssuesError`` so the CLI can exit non-zero with a clear
    operator message rather than a raw ``CalledProcessError``.
    """
    try:
        completed = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--label",
                "ready-for-agent",
                "--state",
                "open",
                "--json",
                "number,title,body,labels",
                "--repo",
                f"{owner}/{repo}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PodiumIssuesError(
            "gh CLI not found in PATH; install it to sync from GitHub"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise PodiumIssuesError(
            f"gh issue list failed (exit {exc.returncode}): {stderr}"
        ) from exc
    try:
        parsed = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise PodiumIssuesError(
            f"gh issue list returned non-JSON output: {exc}"
        ) from exc
    if not isinstance(parsed, list):
        raise PodiumIssuesError("gh issue list returned unexpected payload shape")
    return parsed


def sync_from_github(
    cwd: Path,
    *,
    bindings_path: Path = BINDINGS_PATH,
    dry_run: bool = False,
) -> list[str]:
    """Insert-only reconcile of GitHub child issues into the Podium binding.

    The action is re-runnable: every re-press picks up newly-added child issues
    and heals drift, never duplicating or mutating an existing row. See
    ``docs/adr/0042-github-podium-dispatch-bridge.md`` section 1 for the
    selection rule and provenance gate.
    """
    binding = resolve_binding_for_cwd(cwd, bindings_path)
    repo_path = binding.get("repo_path")
    if not repo_path:
        raise PodiumIssuesError(
            f"binding {binding['name']!r} has no repo_path; cannot infer GitHub repo"
        )
    _worktree_module = import_module("web.api.worktree")
    resolved = _worktree_module.resolve_github_repo(Path(repo_path))
    if resolved is None:
        raise PodiumIssuesError(
            f"binding {binding['name']!r} repo_path {repo_path} does not resolve "
            "to a GitHub remote; Sync from GitHub is opt-in via resolvability "
            "(ADR-0042 section 1)"
        )
    owner, repo = resolved
    external_prefix = f"github:{owner}/{repo}#"
    raw_issues = _run_gh_issue_list(owner, repo)
    child_issues = [
        item
        for item in raw_issues
        if isinstance(item, dict) and _has_parent_section(str(item.get("body") or ""))
    ]
    # `gh issue list` returns newest-first, but `to-tickets` publishes blockers
    # before dependents so blockers carry lower numbers. Insert in ascending
    # number order so a blocker is already mirrored when its dependent's
    # `## Blocked by` edge is resolved within a single sync pass; otherwise the
    # edge is silently dropped (ADR-0042 section 1 dependency ordering).
    child_issues.sort(key=lambda item: int(item["number"]))
    lines = [
        f"binding={binding['name']} repo={owner}/{repo} "
        f"gh_issues={len(raw_issues)} child_issues={len(child_issues)}"
    ]

    worktree_default = binding.get("worktree_default")
    if worktree_default is None:
        worktree_default = binding.get("type", "infra") == "coding"

    if dry_run:
        for item in child_issues:
            number = int(item["number"])
            title = str(item.get("title") or "")
            auto_land = bool(
                _extract_runnable_verification(str(item.get("body") or ""))
            )
            lines.append(
                f"github:{owner}/{repo}#{number} '{title}' "
                f"auto_land={auto_land} -> podium (dry-run)"
            )
        return lines

    now = datetime.now(UTC).isoformat()
    connection = connect()
    inserted = 0
    skipped = 0
    try:
        for item in child_issues:
            number = int(item["number"])
            external_id = f"{external_prefix}{number}"
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "")
            existing = connection.execute(
                "SELECT id FROM issue WHERE external_id = ?", (external_id,)
            ).fetchone()
            if existing is not None:
                skipped += 1
                lines.append(
                    f"github:{owner}/{repo}#{number} '{title}' "
                    f"-> existing podium #{existing['id']} (skip)"
                )
                continue
            blocked_by_ids: list[int] = []
            for ref_number in _extract_blocked_by_numbers(body):
                blocker = connection.execute(
                    "SELECT id FROM issue WHERE external_id = ?",
                    (f"{external_prefix}{ref_number}",),
                ).fetchone()
                if blocker is None:
                    continue
                blocked_by_ids.append(int(blocker["id"]))
            auto_land = bool(_extract_runnable_verification(body))
            _issue_create = cast(Any, import_module("web.api.issue_create"))
            issue_id = _issue_create.insert_issue_row(
                connection,
                binding_name=str(binding["name"]),
                title=title,
                description=body,
                created_at=now,
                base_branch=str(binding.get("base_branch") or "main"),
                preferred_agent=str(binding.get("default_agent") or "pi"),
                preferred_skill="implement",
                worktree_active=bool(worktree_default),
                auto_land=auto_land,
                external_id=external_id,
                # Synced GitHub issues reuse the existing 'automation' origin so
                # the card shows the automation chip with no schema change; a
                # dedicated 'github' origin would need an issue-table rebuild to
                # widen the origin CHECK (cf. migration 0023) and is deferred.
                origin="automation",
                blocked_by=blocked_by_ids,
            )
            connection.commit()
            inserted += 1
            lines.append(
                f"github:{owner}/{repo}#{number} '{title}' "
                f"auto_land={auto_land} -> podium #{issue_id}"
            )
    finally:
        connection.close()
    lines.append(f"inserted={inserted} skipped={skipped}")
    return lines

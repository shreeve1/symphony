#!/usr/bin/env python3
"""Create Podium issues from a JSON slice spec over the dispatch reverse tunnel.

Stdlib-only (urllib/json/os/sys) so it runs on a remote host with no venv and no
Symphony repo checkout (ADR-0036). Reads PODIUM_BASE_URL, PODIUM_API_TOKEN, and
SYMPHONY_BINDING_NAME from the env the harness injects, topologically orders the
slices by their blocked_by keys, POSTs blockers first, and threads the returned
int ids into dependents' blocked_by. Mirrors the local podium-issues
_description() format (web/cli/podium_issues.py) so board issues look identical.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


class RemoteIssuesError(RuntimeError):
    """Operator-facing failure (bad env, bad spec, HTTP error, cycle)."""


def _require_env(name: str) -> str:
    value = os.environ.get(name) or ""
    if not value:
        raise RemoteIssuesError(f"{name} not set; required for podium-issues-remote")
    return value


def _load_slices(spec_path: str) -> list[dict]:
    with open(spec_path, encoding="utf-8") as handle:
        raw = json.load(handle)
    rows = raw.get("slices") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise RemoteIssuesError(f"{spec_path}: expected non-empty 'slices' list")
    slices: list[dict] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise RemoteIssuesError(f"{spec_path}: slice {idx} is not an object")
        key = str(row.get("key") or idx)
        if key in seen:
            raise RemoteIssuesError(f"{spec_path}: duplicate slice key {key!r}")
        seen.add(key)
        title = str(row.get("title") or "").strip()
        verification = str(row.get("verification") or "").strip()
        if not title or not verification:
            raise RemoteIssuesError(
                f"{spec_path}: slice {key!r} needs title+verification"
            )
        acceptance = [str(x) for x in row.get("acceptance", [])]
        if not acceptance:
            raise RemoteIssuesError(f"{spec_path}: slice {key!r} needs acceptance")
        slices.append(
            {
                "key": key,
                "title": title,
                "description": str(row.get("description") or "").strip(),
                "acceptance": acceptance,
                "verification": verification,
                "blocked_by": [str(x) for x in row.get("blocked_by", [])],
                "locks": [str(x) for x in row.get("locks", [])],
                "priority": row.get("priority"),
                "model": row.get("model"),
                "agent": row.get("agent"),
            }
        )
    unknown = sorted({b for s in slices for b in s["blocked_by"]} - seen)
    if unknown:
        raise RemoteIssuesError(f"{spec_path}: unknown blocked_by keys: {unknown}")
    return slices


def _topo_order(slices: list[dict]) -> list[dict]:
    remaining = {s["key"]: s for s in slices}
    emitted: set[str] = set()
    ordered: list[dict] = []
    while remaining:
        ready = [
            s
            for s in slices
            if s["key"] in remaining and all(b in emitted for b in s["blocked_by"])
        ]
        if not ready:
            raise RemoteIssuesError("slice dependency cycle detected")
        for item in ready:
            ordered.append(item)
            emitted.add(item["key"])
            remaining.pop(item["key"])
    return ordered


def _description(slice_: dict) -> str:
    acceptance = "\n".join(f"- [ ] {item}" for item in slice_["acceptance"])
    return (
        f"## What to build\n\n{slice_['description']}\n\n"
        f"## Acceptance criteria\n\n{acceptance}\n\n"
        f"## Verification\n\n{slice_['verification']}\n"
    )


def _payload(slice_: dict, blocked_by_ids: list[int]) -> dict:
    body: dict = {
        "description": _description(slice_),
        "auto_land": True,
        "worktree_active": True,
        "blocked_by": blocked_by_ids,
        "locks": slice_["locks"],
    }
    if slice_.get("priority") is not None:
        body["priority"] = slice_["priority"]
    if slice_.get("model"):
        body["preferred_model"] = slice_["model"]
    if slice_.get("agent"):
        body["preferred_agent"] = slice_["agent"]
    # origin deliberately omitted; API defaults to "operator" (agent acts on the
    # operator's behalf, not a patrol).
    return body


def _post(base: str, binding: str, token: str, payload: dict) -> int:
    url = f"{base}/api/bindings/{binding}/issues"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RemoteIssuesError(
            f"POST {url} failed: HTTP {exc.code}: {detail}"
        ) from exc
    issue_id = result.get("id")
    if not isinstance(issue_id, int):
        raise RemoteIssuesError(f"POST {url}: response missing int id: {result!r}")
    return issue_id


def create_from_spec(spec_path: str, *, dry_run: bool = False) -> list[int]:
    base = _require_env("PODIUM_BASE_URL").rstrip("/")
    binding = _require_env("SYMPHONY_BINDING_NAME")
    token = "" if dry_run else _require_env("PODIUM_API_TOKEN")
    ordered = _topo_order(_load_slices(spec_path))

    key_to_id: dict[str, int] = {}
    created: list[int] = []
    for placeholder, slice_ in enumerate(ordered, start=1):
        # In dry-run no ids come back, so a stable placeholder stands in for the
        # blocker id purely so dependents' payloads render.
        blocked_by_ids = [key_to_id[k] for k in slice_["blocked_by"]]
        payload = _payload(slice_, blocked_by_ids)
        if dry_run:
            print(f"[dry-run] {slice_['key']}: {json.dumps(payload)}")
            key_to_id[slice_["key"]] = placeholder
            continue
        issue_id = _post(base, binding, token, payload)
        key_to_id[slice_["key"]] = issue_id
        created.append(issue_id)
        print(f"created {slice_['key']} -> issue {issue_id}")
    return created


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--dry-run"]
    dry_run = "--dry-run" in argv
    if len(args) != 1:
        print("usage: create_issues.py <spec.json> [--dry-run]", file=sys.stderr)
        return 2
    try:
        create_from_spec(args[0], dry_run=dry_run)
    except RemoteIssuesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

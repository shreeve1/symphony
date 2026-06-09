# Plan: Symphony Operational Improvements

## Task Description

Address three operational gaps in Symphony:

1. **Agent stderr is captured but never surfaced** — `AgentResult` has `stderr` but all completion paths only use `stdout`. When agents crash, the real error is often in stderr.
2. **No concurrency guard across containers** — The lock file (`/tmp/symphony.lock`) is inside the container. If two containers start, each has its own `/tmp`, so both can claim the same issue.
3. **Build mode relies on agent reading comment history** — `plane_cli.py` has no `plane comments` command. The agent must infer from the issue description alone.

## Objective

Surface stderr in comments, prevent double-claim races, give build-mode agents a way to read plan history.

## Solution Approach

1. Add `_format_report()` that returns separate stdout/stderr sections; callers emit each as its own fenced block (avoids nested fences).
2. Update `from_env()` to derive lock_path from `homelab_repo_path` when `SYMPHONY_LOCK_PATH` is not set.
3. Add `plane comments` command that fetches and prints comments oldest-first.

## Relevant Files

- `/home/james/plane/symphony/scheduler.py` — `_sanitize_report`, completion paths
- `/home/james/plane/symphony/plane_cli.py` — add `comments` command
- `/home/james/plane/symphony/config.py` — `lock_path` default in `from_env()`
- `/home/james/plane/symphony/tests/test_scheduler.py` — stderr tests
- `/home/james/plane/symphony/tests/test_plane_cli.py` — comments command tests
- `/home/james/homelab/.gitignore` — add `.symphony.lock`
- `/home/james/homelab/WORKFLOW.md` — update build mode instructions

## Step by Step Tasks

### 1. Surface stderr in completion comments

- [ ] [1.1] In `scheduler.py`, add `_format_report(result, secrets)` that returns a tuple `(stdout_section, stderr_section)`. Each section is either empty string or `**Label:**\n{sanitized_text}`. Sanitize stdout and stderr independently via `_sanitize_report()`.
- [ ] [1.2] Update all 5 completion paths (done, review, plan, timeout, nonzero) to call `_format_report()`. Each path emits stdout as `**Agent Report:**\n```\n{stdout}\n````, then stderr as `**Stderr:**\n```\n{stderr}\n``` if non-empty. These are sibling sections (not nested).
- [ ] [1.3] Fix `_sanitize_report` truncation to be byte-precise: truncate the encoded bytes, then decode with `errors="replace"`.

### 2. Move lock file to shared repo path

- [ ] [2.1] In `config.py:from_env()`, change the lock_path fallback from `"/tmp/symphony.lock"` to `str(Path(source["HOMELAB_REPO_PATH"]) / ".symphony.lock")` when `SYMPHONY_LOCK_PATH` is not set.
- [ ] [2.2] Add `.symphony.lock` to `/home/james/homelab/.gitignore`.

### 3. Add `plane comments` command

- [ ] [3.1] Add `comments` command to `run()` that calls `client.get(config.comment_path())` and prints each comment's `comment_html` field to stdout. Sort by `created_at` oldest-first if available. Separate entries with `---`.
- [ ] [3.2] Update usage string to include `comments`.

### 4. Update WORKFLOW.md build mode instructions

- [ ] [4.1] In WORKFLOW.md Build Mode section, add: "Use `plane comments` to read the plan from the issue's comment history. Find the approved plan comment. If no plan is found, call `plane blocked`."

### 5. Write tests

- [ ] [5.1] Test: stderr appears in done comment when non-empty, in its own fenced block
- [ ] [5.2] Test: stderr appears in blocked comment (timeout) when non-empty
- [ ] [5.3] Test: stderr absent from comment when empty
- [ ] [5.4] Test: secrets in stderr are redacted
- [ ] [5.5] Test: lock path defaults to `{homelab_repo_path}/.symphony.lock` when SYMPHONY_LOCK_PATH unset
- [ ] [5.6] Test: SYMPHONY_LOCK_PATH overrides the default
- [ ] [5.7] Test: `plane comments` fetches and displays comments oldest-first
- [ ] [5.8] Test: `plane comments` with no comments shows empty result

### 6. Validate

- [ ] [6.1] Run `python3 -m pytest` from `/home/james/plane/symphony` — all tests pass
- [ ] [6.2] Verify `.symphony.lock` is effective via `git -C /home/james/homelab check-ignore -q .symphony.lock`

## Progress

**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/11` tasks complete
- Tests: `0/8` tests passing

**Last Updated:** `---`

## Acceptance Criteria

1. Agent stderr appears in Plane completion comments as a sibling fenced section when non-empty
2. Lock file lives in the homelab repo path, preventing dual-container double-claims
3. `plane comments` fetches and displays issue comments oldest-first for agent use
4. WORKFLOW.md tells agents to use `plane comments` in build mode
5. All existing + new tests pass

## Validation Commands

```bash
cd /home/james/plane/symphony && python3 -m pytest tests/ -v
cd /home/james/homelab && git check-ignore -q .symphony.lock
```

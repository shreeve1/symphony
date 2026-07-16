# Plan: Remote Binding File Browser

## Task Description
Extend Podium's existing file browser/editor API so a binding with `remote:` in `bindings.yml` can browse, read, write, create, and delete files in its remote `repo_path`. The current endpoints operate on a local `Path`, causing the n8n browser request to fail. The frontend already consumes stable endpoint schemas, so this is a backend-only transport extension.

## Objective
A logged-in operator can use the existing `/[binding]/files` UI for a remote binding with the same endpoint contracts and safeguards as a local binding: lazy directory listing, text reads, text writes, file creation, and deletion remain scoped to the remote checkout root.

## Problem Statement
`web/api/files.py` resolves every binding `repo_path` then directly calls local filesystem APIs (`os.scandir`, `Path.read_text`, `write_text`, and `unlink`). For remote bindings such as n8n, that path belongs to the SSH host, not the Podium API host. The existing remote attachment transport already demonstrates the accepted connection policy (`ssh_base_args(remote)`), but the file endpoints do not select a remote implementation.

## Solution Approach
Keep the five HTTP endpoints and their JSON schemas unchanged. In `web/api/files.py`, add a small server-side remote operation helper selected through `main._is_remote_binding(name)` and `main._remote_for_binding(name)`. It invokes `ssh_support.ssh_base_args(remote)` (the project-root import already used by `attachments.py`) and runs one SSH command per API operation.

That command uses a fixed `python3 -c` bootstrap plus a base64-encoded embedded stdlib helper: the bootstrap decodes the helper without passing its multiline source through a remote shell. The helper receives one JSON request on stdin (including write content), resolves the remote root and target/parent, checks containment, performs the requested action, and emits one JSON result envelope. Command arguments are `shlex.quote`-escaped, matching existing remote attachment/worktree transport; operator paths and content never become shell fragments. This is deliberately one remote process per operation, so canonicalization, the required pre-read `stat` size check, listing, and the action share one SSH round trip. It requires `python3` on remote binding hosts; verify that prerequisite during the n8n smoke rather than adding a daemon, SFTP dependency, or new credential.

The helper must reject traversal and remote symlink escapes exactly as the local helper does. For create/write, resolve and contain the existing parent before creating missing directories, then re-check the resulting target/parent before writing. Translate structured remote domain errors to the current 4xx semantics, SSH command failures to 502, and subprocess timeouts to 504 so remote unavailability never appears as an unhandled 500. `absolute_path` remains in the listing schema and intentionally means the remote host's absolute path for remote bindings; the frontend treats it as a display/copy value, not a local API-host path.

## Relevant Files
Use these files to complete the task:

- `web/api/files.py` — add remote-binding detection, SSH operation transport, remote canonical-path containment, and endpoint branches while retaining local behavior and response shapes.
- `web/api/tests/test_files.py` — extend the existing temporary-repo/TestClient fixture with a mocked remote binding and assert remote transport, endpoint parity, containment, and failure mapping.

## Implementation Phases
### Phase 1: Remote transport and safety
Add the SSH-backed operation helper and make its remote-root containment checks enforce the same boundary as local file access.

### Phase 2: Endpoint parity and regression tests
Route all five endpoints through the helper when appropriate, add mocked contract coverage, and smoke the n8n binding.

## Step by Step Tasks
IMPORTANT: Execute every step in order when running manually. `/dev-build` will parallelize independent groups automatically.

### 1. Add a constrained remote file-operation helper [sequential]
- [x] [1.1] In `web/api/files.py`, resolve `main._is_remote_binding(name)` and `main._remote_for_binding(name)` through the already-loaded `main` module alongside `_repo_path_for_binding`; select SSH only for remote bindings, leaving all local-binding calls unchanged.
- [x] [1.2] In `web/api/files.py`, add `import subprocess` plus one embedded remote `python3` standard-library helper for list, read, write, create, and delete. Base64-encode its source and invoke it through a fixed `python3 -c` bootstrap as one `ssh_support.ssh_base_args(remote) + [command]` call; construct command arguments with `shlex.quote` (same convention as `attachments.py`) and send one JSON request—including write content—through subprocess stdin. Return a JSON stdout envelope for directory entries, file metadata/content, and typed domain errors.
- [x] [1.3] In the remote helper, reject absolute/upward paths, resolve the remote root and existing target or parent, require the canonical target to remain beneath the canonical root (including symlink escapes), and re-check parent/target after any directory creation. Batch that containment work with the requested operation in the same remote process; for reads, run `stat` before returning content and enforce `MAX_FILE_SIZE` before transmission.
- [x] [1.4] In `web/api/files.py`, convert structured remote missing targets, type conflicts, binary/size violations, and invalid parents into the local endpoint's existing 4xx responses; convert SSH non-zero/invalid protocol output to 502 and subprocess timeouts to 504. Preserve `absolute_path` in list results as the remote host path.

### 2. Route all file endpoints through the remote helper [sequential]
- [x] [2.1] Update `list_directory` and `read_file` in `web/api/files.py` to dispatch to the remote helper for remote bindings and return the unchanged local response schemas (`DirListing` and `FileContent`).
- [x] [2.2] Update `write_file`, `create_file`, and `delete_file` in `web/api/files.py` to dispatch remotely while retaining their editable-type, size, conflict, parent-path, and response-contract behavior.
- [x] [2.3] Keep the existing SQLite binding-row gate and FastAPI auth behavior intact; do not modify frontend API types or components because they already consume these endpoint schemas.

### 3. Verify remote behavior without touching live repos [sequential]
- [x] [3.1] In `web/api/tests/test_files.py`, add a separately-scoped remote fixture with `remote: {host, user}` and mock `web.api.files.subprocess.run`; assert every endpoint emits the existing SSH base args, invokes the one-process base64/bootstrap `python3` protocol with JSON stdin, and returns its current JSON shape without using a local remote `repo_path`.
- [x] [3.2] In `web/api/tests/test_files.py`, compile the decoded embedded helper before mocking it, then cover remote traversal and simulated remote symlink-escape rejection, pre-read oversized-file rejection, missing/read-directory/create-conflict/invalid-parent mappings, binary reads/writes, malformed remote protocol/SSH failure → 502, and timeout → 504; retain all local regression coverage.
- [ ] [3.3] Run the focused tests and static checks, then verify `python3` is available on n8n and manually open `/n8n/files` against the deployed API to exercise list → read → create/write → delete on a disposable file. Confirm no browser-console 500s and remove the disposable file.

## Testing Strategy
- **API contract tests:** use the existing FastAPI `TestClient`, `_bindings_override`, and a mocked subprocess so no test contacts n8n or writes a live remote checkout.
- **Safety tests:** prove absolute/upward paths and simulated remote symlink escapes are refused before data access; prove parent/type/conflict checks retain local status codes.
- **Transport tests:** compile the decoded embedded helper, assert `ssh_base_args` is used, every operation is one SSH process, paths are `shlex.quote`-escaped, JSON request content uses stdin, pre-read size checks occur remotely, and failed/timed-out SSH commands map to 502/504.
- **Manual integration:** verify n8n has `python3`, then perform one n8n UI smoke against a disposable text file only after automated coverage passes.

## Tests
### T.1. Remote endpoint parity
- [ ] [T.1.1] List and read remote files return the same fields and status codes as their local counterparts.
- [ ] [T.1.2] Write, create, and delete remote files return the existing success payloads and preserve editable/size constraints.

### T.2. Remote safety and failure handling
- [ ] [T.2.1] Traversal, absolute paths, and remote symlink escapes are rejected without dispatching an unsafe filesystem operation.
- [ ] [T.2.2] Missing files, directory/type conflicts, invalid parents, binary/oversized content, malformed remote output, SSH failure, and SSH timeout produce defined 4xx/502/504 responses rather than 500.

### T.3. Live smoke
- [ ] [T.3.1] The n8n file UI completes list, read, disposable create/write, and delete with no browser-console errors.

## Progress
**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/7` tasks complete
- Tests: `0/5` tests passing

**Last Updated:** `---`

## Acceptance Criteria
- All five `/api/bindings/{name}/files...` operations work for remote bindings through the configured SSH transport and keep their current response schemas.
- Local binding behavior remains unchanged.
- Remote targets cannot escape `repo_path` through absolute paths, traversal, or symlinks.
- Remote command failure and timeout return actionable 502/504 API responses, never an unhandled 500.
- Focused automated tests pass without network access or live repository writes.
- The n8n UI smoke completes full file-browser CRUD on a disposable file with no 500 console error.

## Testing Promise
`web/api/tests/test_files.py` proves local regression coverage and full mocked remote endpoint parity, safety, and error mapping; the n8n UI smoke proves the deployed SSH path works without leaving a file behind.

## Validation Commands
Execute these commands to validate the task is complete:

- `uv run pytest web/api/tests/test_files.py -q` — local and mocked remote file endpoint tests pass.
- `uv run ruff check web/api/files.py web/api/tests/test_files.py` — touched Python code passes linting.
- `uv run python -m py_compile web/api/files.py` — file endpoint module compiles.

## Notes
- Import `ssh_base_args` as `from ssh_support import ssh_base_args`, matching `web/api/attachments.py`; it lives at the project root, not under `web/api/`. `files.py` will also import `subprocess`, so the targeted subprocess mock is valid.
- Reuse the existing `ssh_support.ssh_base_args` policy; remote attachments already rely on it. This avoids a second SSH configuration surface. `python3` is the only remote-host prerequisite added by this endpoint transport and is checked in the live smoke.
- The frontend is intentionally untouched: its API functions and browser/editor components already use the response fields retained by this plan; `absolute_path` is display/copy-only and intentionally becomes a remote-host path for remote bindings.
- Reusing the request-time private `main` helpers is consistent with the existing `_binding_repo_root` pattern; promoting them is unrelated refactoring and out of scope.
- This Podium slice does not edit wiki files. If the implementation changes the durable remote-binding contract, capture it in the consolidated post-landing wiki update.

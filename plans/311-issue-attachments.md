# Plan: Issue Attachments for Podium

## Task Description
Implement issue-level attachments for Podium from `docs/handoffs/2026-07-08-311-issue-attachments-prd.md`. Operators can upload screenshots/files from the Issue flyout and, if small enough to keep boring, during new-issue creation. Attachment bytes live outside git under `.symphony/attachments/<issue_id>/` in the binding checkout, metadata lives in Podium SQLite, and every fresh/resume dispatch prompt gets an **Issue Attachments** block with paths the agent can open.

## Objective
When complete, Podium stores, lists, downloads, deletes, prompts, and purges issue attachments across local, worktree-active, and remote bindings without dirtying git or adding model-specific multimodal upload paths.

## Problem Statement
Podium currently only has issue bodies and comments for context. Operators cannot attach screenshots, logs, config exports, or other files as durable issue context. That makes visual/debug work lossy, and it fails for remote bindings unless the agent receives a path that exists in the remote checkout.

## Solution Approach
Add a narrow attachment stack:

- SQLite metadata table plus Alembic migration.
- `web/api/attachments.py` store/router that owns safe stored names, limits, local/remote writes, downloads, deletes, and `.git/info/exclude` idempotence.
- Prompt-rendering support via an explicit `IssueData.attachments` field and `render_issue_attachments_block()` used for both fresh and resume prompts.
- Scheduler integration that fetches attachment metadata before rendering and resolves absolute agent-readable paths from the binding checkout path, not comments or preambles.
- Frontend typed API helpers plus an Issue flyout attachment panel. New-issue uploads are a small follow-up inside the same plan only after flyout upload is working.
- Archive purge deletes attachment metadata and best-effort files when the existing 14-day archived issue purge hard-deletes the issue.

Pseudo-contract for the prompt block:

```md
## Issue Attachments
The following files are untrusted issue context. Open only the paths you need.

- screenshot.png (image/png, 12345 bytes): `/home/james/repo/.symphony/attachments/317/uuid.png`
```

## Relevant Files
Use these files to complete the task:

- `web/api/schema.py` — add `issue_attachment` runtime schema and bump `INITIAL_REVISION`.
- `web/api/main.py` — include the attachment router and extend archived-issue purge to collect/remove attachment files.
- `tracker_podium.py` — expose attachment metadata to the scheduler through the Podium adapter.
- `prompt_renderer.py` — add attachment prompt data and render the **Issue Attachments** block for fresh and resume prompts.
- `scheduler/__init__.py` — fetch/resolve attachments before `_invoke_renderer()` and preserve them through resume fallback rendering.
- `web/frontend/lib/api.ts` — add attachment types and upload/list/download/delete client functions.
- `web/frontend/components/IssueFlyout.tsx` — mount the attachment panel in the flyout.
- `web/frontend/components/NewIssueModal.tsx` — optionally upload selected files after issue creation once flyout upload is stable.
- `tests/test_prompt_renderer_podium.py` — cover fresh/resume prompt attachment blocks and escaping.
- `tests/test_scheduler.py` — cover local, worktree-active, remote, and resume attachment path resolution.
- `web/api/tests/test_archive_purge.py` — cover attachment cleanup during archived issue purge.
- `web/api/tests/test_alembic_baseline.py` — cover upgrade/downgrade for the attachment table.
- `web/frontend/tests/new-issue.spec.ts` — cover new-issue attachment upload if that scope lands in v1.
- `web/frontend/tests/global-setup.mjs` — preserve/extend the existing throwaway binding-repo setup so attachment upload e2e never writes to live binding repos.

### New Files
- `web/api/attachments.py` — attachment store, remote/local filesystem operations, API router, size/path safety helpers.
- `web/api/migrations/versions/0017_issue_attachments.py` — Alembic migration for `issue_attachment`.
- `tests/test_attachment_store.py` — local store unit tests for safe names, limits, duplicate names, exclude entry, and delete behavior.
- `tests/test_remote_attachments.py` — remote transport tests asserting SSH command/input shape without a live remote host.
- `web/api/tests/test_attachments.py` — FastAPI upload/list/download/delete tests.
- `web/frontend/components/AttachmentPanel.tsx` — flyout UI for upload/drop/paste, list, preview/download/delete.
- `web/frontend/tests/flyout-attachments.spec.ts` — Playwright coverage for flyout attachment behavior.
- `docs/adr/0035-issue-attachments-storage.md` — ADR for checkout-local attachment storage and lifecycle.

## Implementation Phases
### Phase 1: Metadata and storage core
Create the table/migration and a small store module. Keep all path safety, stored-name generation, limits, and exclude management behind one tested API.

### Phase 2: API and lifecycle
Expose upload/list/download/delete endpoints, then hook archived-issue purge so file cleanup and metadata cleanup share the existing retention lifecycle.

### Phase 3: Prompt and dispatch integration
Render attachment context from scheduler-owned data for fresh and resume dispatches. Resolve paths per binding execution environment.

### Phase 4: Frontend flyout UI
Add the attachment panel to the Issue flyout: picker/drop/paste, list, image preview, download, delete.

### Phase 5: New issue upload and documentation
Add create-flow uploads if the panel/API shape stays small; otherwise leave a documented follow-up. Add the ADR.

### Phase 6: Validation and slice handoff
Run backend, scheduler, prompt, and frontend checks; then route this large plan through issue slicing.

## Step by Step Tasks
IMPORTANT: Execute every step in order when running manually. `/dev-build` will parallelize independent groups automatically.

### 1. Add attachment metadata schema [sequential]
- [ ] [1.1] Modify `web/api/schema.py` to add `issue_attachment(id, issue_id, display_name, stored_name, content_type, size_bytes, storage_rel_path, created_at)` with `issue_id REFERENCES issue(id) ON DELETE CASCADE`, plus indexes on `issue_id` and `(issue_id, stored_name)`.
- [ ] [1.2] Create `web/api/migrations/versions/0017_issue_attachments.py` with upgrade/downgrade for the same table/indexes.
- [ ] [1.3] Modify `web/api/schema.py` to bump `INITIAL_REVISION` to `0017_issue_attachments`.
- [ ] [1.4] Modify `web/api/tests/test_alembic_baseline.py` to verify upgrade from `0016_skill_scope_null_safe_unique` to head creates `issue_attachment`, and downgrade removes it.

### 2. Build the local attachment store [sequential]
- [ ] [2.1] Create `web/api/attachments.py` constants for `.symphony/attachments`, an upload byte cap, accepted empty-file policy, and a single `.git/info/exclude` line for `.symphony/attachments/`.
- [ ] [2.2] Create `web/api/attachments.py` helpers for display-name normalization and collision-resistant stored filenames using stdlib only (`uuid.uuid4`, `pathlib`, `mimetypes`).
- [ ] [2.3] Create `web/api/attachments.py` local write/read/delete functions that always resolve under `<repo_path>/.symphony/attachments/<issue_id>/` and never trust client paths.
- [ ] [2.4] Create `web/api/attachments.py` an idempotent exclude writer for local repos that appends `.symphony/attachments/` to `.git/info/exclude` when `.git/info` exists.
- [ ] [2.5] Create `tests/test_attachment_store.py` for traversal-like filenames, duplicate display names, empty/oversized reject, exclude idempotence, delete missing-file tolerance, and no writes outside `.symphony/attachments/<issue_id>/`.

### 3. Add remote attachment transport [sequential]
- [ ] [3.1] Extend `web/api/attachments.py` with remote write/read/delete helpers using `ssh_support.ssh_base_args(remote)` and binary `subprocess.run(input=bytes)`; do not use `SshClaudeHost.write_text()` because attachments may be binary.
- [ ] [3.2] In `web/api/attachments.py`, make remote writes create the same remote directory under the binding checkout and render/store the remote absolute path, not a local temp mirror.
- [ ] [3.3] Create `tests/test_remote_attachments.py` asserting quoted `mkdir -p`, `cat >`, `cat`, and `rm -f` command shapes plus byte input, with no live SSH.

### 4. Expose attachment API endpoints [sequential]
- [ ] [4.1] Create `web/api/attachments.py` APIRouter endpoints: `GET /api/issues/{issue_id}/attachments`, `POST /api/issues/{issue_id}/attachments`, `GET /api/issues/{issue_id}/attachments/{attachment_id}`, and `DELETE /api/issues/{issue_id}/attachments/{attachment_id}`.
- [ ] [4.2] In `web/api/attachments.py`, make upload validate issue existence, binding row/config, size, and display filename; write bytes first, insert metadata second, and remove the file if the DB insert fails.
- [ ] [4.3] In `web/api/attachments.py`, make list return metadata only; make download return bytes with stored content type and `Content-Disposition` using the display filename.
- [ ] [4.4] In `web/api/attachments.py`, make delete verify the attachment belongs to the issue, delete metadata and file together, tolerate already-missing files, and return the updated list or deleted id.
- [ ] [4.5] Modify `web/api/main.py` to include the attachment router under the existing `/api/*` auth middleware.
- [ ] [4.6] Create `web/api/tests/test_attachments.py` covering upload/list/download/delete, unknown issue, wrong attachment id, empty/oversized upload, binary roundtrip, and remote-helper invocation via a fake binding.

### 5. Hook archived purge lifecycle [sequential]
- [ ] [5.1] Modify `web/api/main.py` `_purge_archived_issues()` to collect attachment rows before deleting each archived issue.
- [ ] [5.2] Modify `web/api/main.py` `_purge_archived_issues()` to delete attachment rows through issue FK cascade, then best-effort unlink local files or remote files after commit; missing files must not abort purge.
- [ ] [5.3] Modify `web/api/tests/test_archive_purge.py` to assert old archived issues purge attachment rows/files, young archived issues keep them, non-archived issues keep them, and missing attachment files do not roll back issue deletion.

### 6. Feed attachments into prompts [sequential]
- [ ] [6.1] Modify `prompt_renderer.py` `IssueData` to carry attachment metadata/path entries without reading files.
- [ ] [6.2] Modify `prompt_renderer.py` to add `render_issue_attachments_block()` that escapes untrusted display names/content types and emits no block for an empty list.
- [ ] [6.3] Modify `prompt_renderer.py` fresh prompt rendering to place **Issue Attachments** before `<issue>` and after any scheduler context/comment block.
- [ ] [6.4] Modify `prompt_renderer.py` resume prompt rendering to include **Issue Attachments** alongside the output contract, schedule context, and newest operator reply.
- [ ] [6.5] Modify `tests/test_prompt_renderer_podium.py` to cover fresh prompt, resume prompt, empty list omission, and escaping of malicious filenames/content types.

### 7. Resolve attachment paths at dispatch [sequential]
- [ ] [7.1] Modify `tracker_podium.py` to expose `list_issue_attachments(issue_id)` returning metadata needed by the scheduler without attachment bytes.
- [ ] [7.2] Modify `scheduler/__init__.py` `_render_for_dispatch()` to call the adapter helper, resolve each `storage_rel_path` against `binding.repo_path`, and pass absolute paths into `IssueData` before `_invoke_renderer()`.
- [ ] [7.3] Modify `scheduler/__init__.py` resume fallback rendering to reuse the same attachment loading/resolution path so resume never drops attachment context.
- [ ] [7.4] Modify `tests/test_scheduler.py` to cover local base checkout, local worktree-active dispatch, remote binding path rendering, fresh prompt, and resume fallback prompt.

### 8. Add frontend API client support [parallel-safe]
- [ ] [8.1] Modify `web/frontend/lib/api.ts` to add `IssueAttachment` metadata types and `fetchIssueAttachments(issueId)`.
- [ ] [8.2] Modify `web/frontend/lib/api.ts` to add `uploadIssueAttachment(issueId, file)` using `FormData`.
- [ ] [8.3] Modify `web/frontend/lib/api.ts` to add `deleteIssueAttachment(issueId, attachmentId)` and a download URL helper for the binary endpoint.

### 9. Build the Issue flyout attachment panel [sequential]
- [ ] [9.1] Create `web/frontend/components/AttachmentPanel.tsx` with React Query list/upload/delete hooks keyed by `['issue-attachments', issue.id]`.
- [ ] [9.2] Create `web/frontend/components/AttachmentPanel.tsx` file picker and drag/drop upload controls with accessible labels and visible pending/error states.
- [ ] [9.3] Create `web/frontend/components/AttachmentPanel.tsx` clipboard paste support for image files when `ClipboardEvent.clipboardData.files` is available; ignore text-only paste.
- [ ] [9.4] Create `web/frontend/components/AttachmentPanel.tsx` list rows with display name, MIME type, size, created time, download link, delete button, and cheap image preview for image MIME types.
- [ ] [9.5] Modify `web/frontend/components/IssueFlyout.tsx` to render `AttachmentPanel` near the comments/reply area without changing reply/steer semantics.
- [ ] [9.6] Modify `web/frontend/tests/global-setup.mjs` only if needed to seed attachment-specific fixture data, and assert the attachment specs use its `PODIUM_BINDINGS_PATH` throwaway repos rather than live binding `repo_path` values.
- [ ] [9.7] Create `web/frontend/tests/flyout-attachments.spec.ts` for list render, upload, image preview, download link, delete update, drag/drop, paste image, keyboard-reachable controls, and no dirty changes in the live binding repos.

### 10. Add new issue upload if still cheap [parallel-safe]
- [ ] [10.1] Modify `web/frontend/components/NewIssueModal.tsx` to stage selected files before submit without adding them to the issue create JSON body.
- [ ] [10.2] Modify `web/frontend/components/NewIssueModal.tsx` submit flow to create the issue, upload staged files to the returned issue id, then invalidate issue queries; if any upload fails, keep the issue and show a clear upload error.
- [ ] [10.3] Modify `web/frontend/tests/new-issue.spec.ts` to cover create-with-attachment only after flyout attachment tests pass, using the same throwaway binding repo isolation as `flyout-attachments.spec.ts`.

### 11. Document storage and lifecycle decision [parallel-safe]
- [ ] [11.1] Create `docs/adr/0035-issue-attachments-storage.md` documenting checkout-local storage, DB metadata, remote writes, prompt-path contract, retention purge, and rejected alternatives: comments, DB BLOBs, object storage, per-run temp mirrors, and multimodal bytes.

### 12. Validate the full feature [sequential]
- [ ] [12.1] Run backend/schema tests with `uv run pytest tests web/api/tests`.
- [ ] [12.2] Run frontend checks with `pnpm --dir web/frontend exec tsc --noEmit` and `pnpm --dir web/frontend test:e2e`.
- [ ] [12.3] Manually confirm `git status --short` in a local test binding stays clean after upload because `.symphony/attachments/` is excluded.

## Testing Strategy
- Unit tests in `tests/` cover pure storage, prompt rendering, scheduler path resolution, and remote transport command construction.
- API integration tests in `web/api/tests/` cover upload/list/download/delete, auth-covered endpoints, schema migration, and archive purge lifecycle.
- E2E tests in `web/frontend/tests/` cover the Issue flyout attachment UX and optional new-issue uploads.
- Edge cases: duplicate filenames, malicious filenames, empty files, oversize files, binary roundtrip, missing files during delete/purge, remote write/read/delete, local worktree-active dispatch, resume dispatch, archived issue purge.

## Tests
### T.1. Schema and storage
- [ ] [T.1.1] Migration upgrade/downgrade creates/removes `issue_attachment` and runtime schema matches head.
- [ ] [T.1.2] Store rejects empty/oversized uploads and path-like display names cannot escape the attachment directory.
- [ ] [T.1.3] Duplicate display names produce distinct stored filenames without overwriting bytes.
- [ ] [T.1.4] `.git/info/exclude` gets exactly one `.symphony/attachments/` entry.

### T.2. API behavior
- [ ] [T.2.1] Upload returns metadata and writes bytes to local attachment storage.
- [ ] [T.2.2] List returns all attachment metadata for the issue only.
- [ ] [T.2.3] Download returns original bytes, content type, and display filename header.
- [ ] [T.2.4] Delete removes row and file; missing file does not prevent row deletion.
- [ ] [T.2.5] Unknown issue, wrong attachment id, empty file, and oversized file return clear 4xx responses.

### T.3. Prompt and dispatch
- [ ] [T.3.1] Fresh Podium prompts include **Issue Attachments** when attachments exist.
- [ ] [T.3.2] Resume prompts include **Issue Attachments** and still include newest operator reply.
- [ ] [T.3.3] Empty attachment lists omit the block.
- [ ] [T.3.4] Local, worktree-active, and remote bindings render absolute paths valid for the agent execution environment.

### T.4. Purge lifecycle
- [ ] [T.4.1] Old archived issue purge deletes attachment rows and files.
- [ ] [T.4.2] Young archived and non-archived issues keep attachment rows and files.
- [ ] [T.4.3] Missing attachment files do not roll back issue/run cleanup.

### T.5. Frontend UX
- [ ] [T.5.1] Flyout lists attachments with name, MIME type, size, download, and delete controls.
- [ ] [T.5.2] File picker and drag/drop upload refresh the list.
- [ ] [T.5.3] Pasted screenshot uploads when clipboard image files exist.
- [ ] [T.5.4] Image attachments show a cheap preview and controls are keyboard-accessible.
- [ ] [T.5.5] New issue modal uploads staged files after create if included in v1.
- [ ] [T.5.6] Attachment e2e uploads write only under Playwright throwaway binding repos, never live binding repos.

## Progress
**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/47` tasks complete
- Tests: `0/22` tests passing

**Last Updated:** `---`

## Acceptance Criteria
- Operators can upload, list, download, preview, and delete issue attachments from the Issue flyout.
- Attachment bytes are stored under `.symphony/attachments/<issue_id>/` in the binding checkout and do not appear in git status for local bindings.
- Remote binding uploads write bytes into the remote checkout, and prompt paths point at the remote path.
- Fresh and resume dispatch prompts include an **Issue Attachments** block with metadata and absolute readable paths.
- Archived issue purge removes attachment metadata and best-effort files after the existing retention window.
- Uploads enforce auth, issue ownership, size limits, empty-file policy, and path traversal safety.
- No direct multimodal/model-specific byte injection is added.
- ADR 0035 records the storage/lifecycle decision and rejected alternatives.

## Testing Promise
All storage, API, scheduler, prompt-rendering, archive-purge, and frontend attachment tests pass with zero failures; full backend pytest and frontend e2e checks pass with no new git-dirty artifacts from attachment storage.

## Validation Commands
Execute these commands to validate the task is complete:

- `uv run pytest tests web/api/tests` — run backend, scheduler, prompt, migration, storage, remote transport, and API tests.
- `pnpm --dir web/frontend exec tsc --noEmit` — verify frontend TypeScript.
- `pnpm --dir web/frontend test:e2e` — run Podium frontend e2e, including attachment specs.
- `git status --short` — verify attachment fixture uploads do not leave source-controlled changes.

## Notes
- Source PRD has no `#req-*` tags, so no traceability map is emitted.
- Use stdlib for names/MIME where possible; no new backend dependencies are needed.
- `FormData` upload is enough for v1. Do not add direct model multimodal APIs, OCR, public URLs, object storage, versioning, search, or per-comment ownership.
- New-issue upload is intentionally last: ship flyout upload first if create-flow staging makes the slice too large.
- Attachment e2e must reuse the existing `web/frontend/tests/global-setup.mjs` throwaway binding repos (`PODIUM_BINDINGS_PATH`) so upload tests never write under live `/home/james/...` binding paths.
- Deploy order matters: run `uv run alembic upgrade head` before restarting `podium-api`, because `ensure_schema()` will fail loudly on a live DB missing the new `issue_attachment` table.
- Because this is a Podium slice run, wiki updates are skipped per ADR-0028; the durable design record is the ADR task above.

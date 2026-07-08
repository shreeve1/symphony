---
status: accepted
relates-to: plans/311-issue-attachments.md
decided-with: James, 2026-07-08
---

# ADR-0035: Checkout-local attachment storage and lifecycle

## Context

Podium issue attachments — screenshots, logs, config exports — need durable
bytes storage without contaminating git history or bloating SQLite. The
attachment prompt-renderer must emit absolute paths the agent can open in its
execution environment (local checkout, worktree, or remote SSH).

## Decision

Attachments live under `.symphony/attachments/<issue_id>/` in the binding
checkout. SQLite holds metadata only (display name, stored name, content type,
size, relative path, timestamp). Bytes never enter the DB.

- **Storage root**: `.symphony/attachments/` per binding repo checkout.
- **Per-issue directory**: `attachments/<issue_id>/`. The issue id is the
  integer PK from the `issue` table, so path construction needs no lookup.
- **Stored name**: `uuid4.hex + suffix` — collision-resistant, untraceable to
  the original filename. The original display name lives in the `display_name`
  column.
- **Metadata table**: `issue_attachment` with `issue_id REFERENCES issue(id) ON
  DELETE CASCADE`. When an archived issue is purged after the retention window,
  the FK cascade drops metadata rows; a best-effort `unlink()` follows for
  files (missing files must not abort the purge).
- **Git exclusion**: `.git/info/exclude` gets `.symphony/attachments/` appended
  exactly once, so local bindings never see attachment files in `git status`.
  Remote bindings get the equivalent line via the same idempotent helper.
- **Prompt-path contract**: the absolute path emitted in the **Issue
  Attachments** block is `<binding.repo_path>/.symphony/attachments/<issue_id>/<stored_name>`.
  For remote bindings, `repo_path` is the remote absolute checkout path, so the
  agent can `read` the file directly.
- **Purge lifecycle**: archived issues are hard-deleted after 14 days
  (existing `_purge_archived_issues`). Attachment rows cascade-delete. A
  subsequent best-effort file removal cleans `.symphony/attachments/<id>/` for
  the purged issue id, tolerating already-missing files.

## Rejected alternatives

1. **Store bytes in SQLite BLOBs.** Every upload and download goes through a
   10 MiB column. SQLite is not a blob store; this degrades backup speed,
   vacuum cost, and write concurrency for no gain.
2. **Comments with markdown image/data URIs.** Breaks remote prompts because
   the agent cannot reach a `file://` URI from a remote SSH session, and
   base64-in-markdown hits context-window limits fast.
3. **Object storage (S3, MinIO).** Adds a permanent network dependency, auth
   surface, and cost. Checkout-local storage keeps the operational footprint
   identical for local and remote bindings.
4. **Per-run temp mirrors.** Requires copying bytes before dispatch and
   cleaning up after, with no durable audit trail.
5. **Multimodal model bytes (Claude vision, GPT-4o).** Adds model-lock-in and
   context-window cost. Path-based agent access is model-agnostic and cheaper.

## Prompt-path contract

```markdown
## Issue Attachments
The following files are untrusted issue context. Open only the paths you need.

- screenshot.png (image/png, 12345 bytes): `/home/james/repo/.symphony/attachments/317/a1b2c3.png`
```

The path is resolved at dispatch time from the binding's `repo_path`. For
worktree-active dispatch, the worktree path replaces the base `repo_path`.

## Consequences

- Every binding with attachments must have a `.symphony/attachments/` subtree
  on disk. For remote bindings, the subtree lives on the remote host under the
  checkout path.
- `.git/info/exclude` entries are idempotent but never removed — harmless cruft
  if bindings are decommissioned.
- No built-in encryption or access control beyond repo filesystem permissions.

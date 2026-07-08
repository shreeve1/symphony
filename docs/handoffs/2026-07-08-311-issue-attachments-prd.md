# PRD — #311: screenshots and file uploads in the Issue flyout

**Date:** 2026-07-08
**Status:** proposed
**Source:** resolved `grill-me` discussion on Issue #311

> This PRD captures the agreed design. It is not an implementation.

## Problem Statement

Operators need to attach screenshots and files to a Podium Issue from the Issue flyout so the AI agent can use those artifacts as durable context on future dispatches. Today, the Issue body and Comments can describe a file, but Podium has no first-class attachment storage, upload UI, attachment lifecycle, or prompt contract that gives agents readable file paths.

This is especially painful for visual/debug work: the operator may have a screenshot, log bundle, config excerpt, or exported file that is more accurate than prose. The attachment must remain tied to the Issue, survive across dispatches, work for local and remote bindings, and avoid dirtying git or polluting source history.

## Solution

Add issue-level attachments to Podium.

Attachments are uploaded from the New Issue flow or Issue flyout, stored inside the binding checkout under a Symphony-owned ignored folder, tracked in Podium metadata, shown in the flyout, and injected into every dispatch prompt as an **Issue Attachments** block containing agent-readable paths.

Storage is per binding and per issue:

- `.symphony/attachments/<issue_id>/...` inside the binding checkout.
- Symphony manages a repo-local exclude entry so attachments do not appear as git changes.
- Remote bindings store the same folder on the remote checkout over SSH.
- Attachments remain while the issue exists, including during the archived inspection window.
- Attachment files and metadata are purged when the archived issue is hard-deleted after the existing 14-day retention window.

Agents consume attachments by opening referenced paths. Symphony does not inject binary bytes directly into model APIs in v1.

## User Stories

1. As an operator, I want to upload a screenshot to an issue, so that I do not have to describe a visual problem in prose.
2. As an operator, I want to paste a screenshot into the Issue flyout, so that capturing UI state is fast.
3. As an operator, I want to attach files when creating a new issue, so that the first dispatch has all needed context.
4. As an operator, I want to attach files to an existing issue, so that follow-up dispatches can use newly discovered evidence.
5. As an operator, I want attachments to be issue-level, so that every later dispatch can find them without depending on a specific comment.
6. As an operator, I want the flyout to list attached files, so that I can confirm what context the agent will see.
7. As an operator, I want to download an attachment from the flyout, so that I can inspect exactly what was stored.
8. As an operator, I want to delete an attachment from the flyout, so that accidental or obsolete uploads can be removed.
9. As an operator, I want uploaded screenshots to be previewable when cheap, so that I can identify them without downloading.
10. As an operator, I want attachments to persist across multiple runs, so that I do not need to re-upload them after each agent turn.
11. As an operator, I want attachments to survive Session Resume, so that a resumed agent still receives the attachment list.
12. As an operator, I want attachments to survive archive until retention purge, so that archived issue review remains complete.
13. As an operator, I want archived issue purge to remove attachments too, so that old binary files do not accumulate forever.
14. As an operator, I want attachments to work on local bindings, so that agents running on aidev can read the files directly.
15. As an operator, I want attachments to work on remote bindings, so that agents running over SSH get files in the remote checkout.
16. As an operator, I want attachment storage to stay out of git status, so that attachments do not block landing or dirty checks.
17. As an operator, I want attachments stored inside the binding folder, so that issue context lives with the project it belongs to.
18. As an operator, I want the agent prompt to name attachment paths clearly, so that the agent knows what evidence is available.
19. As an agent, I want readable filesystem paths for attachments, so that I can open images/files with my normal tools.
20. As an agent, I want attachment paths to be valid for my actual dispatch location, so that local, worktree, and remote runs do not receive unusable paths.
21. As an agent, I want attachments listed on fresh dispatches, so that first-run context is complete.
22. As an agent, I want attachments listed on resume dispatches, so that follow-up work does not lose file context.
23. As an agent, I want attachment metadata such as filename, MIME type, and size, so that I can decide which files to inspect.
24. As a remote-binding agent, I want attachments already present on the remote host, so that I do not need network access back to aidev to read them.
25. As a developer, I want attachment metadata in the database, so that list/download/delete/purge behavior is queryable and testable.
26. As a developer, I want filesystem writes isolated behind a small store module, so that path safety and exclude management can be tested without the UI.
27. As a developer, I want prompt rendering isolated, so that attachment prompt blocks can be tested without dispatching an agent.
28. As a developer, I want remote attachment writes to reuse the existing SSH execution patterns, so that remote support does not invent a second transport.
29. As a developer, I want attachment storage to be path-traversal safe, so that uploaded filenames cannot escape the attachment directory.
30. As a developer, I want upload limits, so that a large file cannot exhaust disk or memory.
31. As a developer, I want attachment delete to remove metadata and file content together, so that orphan rows and orphan files are rare.
32. As a developer, I want purge to tolerate missing files, so that filesystem drift does not abort database cleanup.
33. As a developer, I want local and remote behavior to share the same conceptual contract, so that prompts do not differ by binding type except for concrete paths.
34. As a developer, I want no model-specific multimodal API path in v1, so that pi and Claude remain supported through one boring contract.
35. As a future maintainer, I want the storage and lifecycle decision documented, so that it is clear why attachments live in the binding checkout and not in comments or the Podium database blob.

## Implementation Decisions

- Build an attachment metadata model linked to an Issue. Store filename, content type, byte size, storage path or storage key, timestamps, and enough binding/issue information to resolve files for list/download/delete/purge.
- Store attachment bytes on disk, not in the comments blob and not as database BLOBs.
- Persist attachment files under a Symphony-owned folder inside the binding checkout: `.symphony/attachments/<issue_id>/`.
- Treat attachments as issue-level context, not comment-level context. The UI may show upload actions near comments, but ownership is the Issue.
- Manage a repo-local exclude entry for `.symphony/attachments/` so files do not dirty the base checkout or issue worktrees.
- Resolve attachment paths per dispatch. The prompt must list paths readable from the agent's actual execution environment, including local base checkout, local issue worktree, and remote checkout.
- Inject an **Issue Attachments** block from the scheduler/prompt-rendering layer, not from any project preamble. Coding bindings can run with no preamble, so this must be engine-owned context.
- Include the attachment block on both fresh and resume prompts. Resume currently carries only the newest operator reply plus explicitly preserved scheduler context; attachments need the same explicit preservation.
- For remote bindings, write attachment files into the remote binding checkout over SSH. The remote path is the path rendered in the prompt.
- Do not persist remote attachments in a temporary per-run folder. The operator chose durable storage inside the binding folder so every dispatch can use the files later.
- Do not place attachments in source-controlled paths or require the project to commit ignore rules. Symphony owns local exclude management.
- Keep attachments through archive. Delete attachment files and metadata when the existing archived-issue purge removes the issue after 14 days.
- Add manual attachment delete from the flyout as an early cleanup path.
- Add upload from the flyout. Add upload from issue creation if it can be done without large extra flow complexity; otherwise ship flyout first and make create-upload a follow-up.
- Support drag/drop and file picker. Clipboard paste for screenshots is desired if cheap in the frontend.
- Use simple path-safe filenames. Preserve the display filename in metadata, but use a collision-resistant stored filename so duplicate names cannot overwrite each other.
- Enforce size limits and reject empty/oversized uploads at the API boundary.
- Enforce path traversal protection for all download/delete paths.
- Authentication follows existing Podium API authentication. No public attachment URLs in v1.
- True multimodal model-byte injection is out of scope. Agents open files by path.
- Storage/lifecycle is ADR-worthy because it is hard to reverse and has real trade-offs: checkout-local files vs Podium-local files vs DB BLOBs vs remote temp mirrors.

### Major modules to build or modify

- **Attachment store module:** owns filesystem layout, safe names, writes, reads, deletes, remote writes, and `.git/info/exclude` management.
- **Attachment metadata layer:** owns database schema, API serialization, list/delete/query helpers, and purge integration.
- **Prompt attachment renderer:** pure module that formats the **Issue Attachments** block from attachment metadata and resolved paths.
- **Dispatch path integration:** resolves attachment paths for local, worktree, and remote dispatches and passes them into prompt rendering for fresh and resume runs.
- **Remote attachment transport:** small SSH-backed writer/reader using the same patterns as existing remote dispatch support.
- **Flyout UI attachment panel:** upload/drop/paste, list, download, delete, and minimal preview.
- **New issue UI upload hook:** optional first release if it stays small; otherwise follow-up.
- **Archive purge hook:** deletes attachment files and metadata when the issue purge deletes the issue.

## Testing Decisions

Good tests should verify external behavior and contracts, not internal implementation details. The highest-value tests are path resolution, prompt rendering, upload/list/download/delete behavior, and purge lifecycle.

Test these modules:

- **Attachment store:** local path creation, safe filename handling, duplicate names, traversal rejection, delete behavior, exclude-entry idempotence.
- **Remote attachment transport:** verifies the expected SSH commands or host-mediated writes without requiring a live remote host.
- **Attachment metadata/API:** upload returns metadata, list includes uploaded files, download returns bytes and content type, delete removes metadata and file, invalid issue/file IDs return correct errors.
- **Prompt renderer:** fresh prompts include the **Issue Attachments** block; resume prompts include it too; empty attachment lists produce no noisy block; paths are escaped as untrusted data.
- **Dispatch path resolution:** local base checkout, local worktree, and remote checkout all produce the path the agent can open.
- **Archive purge:** old archived issues delete attachment rows and files; young archived issues keep them; non-archived issues keep them; missing files do not abort purge.
- **Flyout UI:** attachment list renders, upload succeeds, delete updates the list, and image preview/download controls are accessible.

Prior art in the codebase:

- Existing prompt-renderer tests cover fresh vs resume prompt behavior.
- Existing worktree tests cover git dirty checks, worktree path handling, and ignored Podium-owned directories.
- Existing archive purge tests cover issue/run/log/worktree retention and missing-file tolerance.
- Existing file browser/editor endpoints cover path traversal and file read/write API patterns.
- Existing remote dispatch tests cover SSH command construction and remote filesystem mediation.
- Existing flyout tests cover comments/session UI and mutation-driven cache updates.

## Out of Scope

- Direct multimodal model upload or model-specific image byte injection.
- OCR, image summarization, or automatic screenshot analysis before dispatch.
- Attachment versioning.
- Per-comment attachment ownership.
- Public/shareable attachment URLs.
- Cross-binding attachment reuse.
- Attachment search.
- Rich gallery UI beyond minimal preview/list/download/delete.
- Virus scanning or deep content inspection.
- User-configurable retention policy beyond the existing archived issue purge window.
- Moving attachment storage to object storage.
- Committing attachment files or project `.gitignore` changes.
- Reworking Session Resume beyond adding the attachment block.

## Further Notes

The load-bearing edge case is path correctness. The path shown to the agent must be readable from that dispatch's real environment. A base-checkout-local path is not enough for remote bindings, and a repo-relative path may be wrong for worktree-active runs. Prefer absolute paths in the prompt.

The second load-bearing edge case is resume. If attachment context is only added to the fresh prompt path, the feature fails the agreed requirement that every dispatch can use the files.

This PRD intentionally keeps the v1 contract boring: durable files plus prompt paths. That keeps pi and Claude aligned and avoids coupling Podium attachments to any one model provider's multimodal API.

Because this run is a Podium slice, wiki updates are intentionally skipped per ADR-0028. If implemented, the storage/lifecycle decision should get an ADR or equivalent design note outside the slice run.

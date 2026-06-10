"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchIssue, fetchIssueRuns, type IssueDetail } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { RunHistoryList } from "@/components/RunHistoryList";

// Width persistence — the operator's chosen flyout width survives reopen and
// reload. The #012c spec's "~480px" is only the default; validated by the
// prototype, the panel is resizable from its left edge.
const WIDTH_KEY = "podium-flyout-width";
const DEFAULT_W = 480;
const MIN_W = 360;
const MAX_W = 900;

function useFlyoutWidth() {
  const [width, setWidth] = useState(DEFAULT_W);
  // Tracks the teardown for an in-flight drag so a mid-drag unmount can't leak
  // window listeners (or fire onUp on an unmounted component).
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY));
    if (saved >= MIN_W && saved <= MAX_W) setWidth(saved);
  }, []);

  useEffect(() => () => cleanupRef.current?.(), []);

  const startDrag = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    const clamp = (x: number) =>
      Math.min(MAX_W, Math.max(MIN_W, window.innerWidth - x));
    const onMove = (ev: PointerEvent) => setWidth(clamp(ev.clientX));
    const teardown = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.userSelect = "";
      cleanupRef.current = null;
    };
    const onUp = (ev: PointerEvent) => {
      window.localStorage.setItem(WIDTH_KEY, String(Math.round(clamp(ev.clientX))));
      teardown();
    };
    cleanupRef.current = teardown;
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  return { width, startDrag };
}

function Chip({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value ?? "—"}</span>
    </span>
  );
}

function MetadataChips({ issue }: { issue: IssueDetail }) {
  return (
    <div className="flex flex-wrap gap-1.5" data-testid="metadata-chips">
      <Chip label="state" value={issue.state} />
      <Chip label="skill" value={issue.preferred_skill} />
      <Chip label="agent" value={issue.preferred_agent} />
      <Chip label="model" value={issue.preferred_model} />
      <Chip label="priority" value={issue.priority} />
      <Chip label="worktree" value={issue.worktree_active ? "active" : "off"} />
    </div>
  );
}

const TABS = ["comments", "context"] as const;
type Tab = (typeof TABS)[number];

export function IssueFlyout({
  issueId,
  onClose,
}: {
  issueId: number | null;
  onClose: () => void;
}) {
  const { width, startDrag } = useFlyoutWidth();
  const [tab, setTab] = useState<Tab>("comments");
  const panelRef = useRef<HTMLElement | null>(null);

  const detail = useQuery({
    queryKey: ["issue", issueId],
    queryFn: () => fetchIssue(issueId as number),
    enabled: issueId != null,
  });
  const runs = useQuery({
    queryKey: ["runs", issueId],
    queryFn: () => fetchIssueRuns(issueId as number),
    enabled: issueId != null,
  });

  // Reset to Comments each time a different issue opens.
  useEffect(() => setTab("comments"), [issueId]);

  // Escape closes (click-outside is handled by the backdrop).
  useEffect(() => {
    if (issueId == null) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [issueId, onClose]);

  // Focus management: move focus into the panel on open, restore it on close.
  useEffect(() => {
    if (issueId == null) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previouslyFocused?.focus?.();
  }, [issueId]);

  if (issueId == null) return null;

  const issue = detail.data;

  return (
    <>
      <div
        data-testid="flyout-backdrop"
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        data-testid="issue-flyout"
        role="dialog"
        aria-modal="true"
        aria-labelledby="flyout-title"
        tabIndex={-1}
        style={{ width }}
        className="fixed inset-y-0 right-0 z-50 flex overflow-hidden border-l bg-background shadow-xl outline-none"
      >
        {/* Resize handle — drag the left edge. Lives on the non-scrolling
            wrapper so it stays put while the body scrolls. */}
        <div
          onPointerDown={startDrag}
          className="group absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize"
          role="separator"
          aria-orientation="vertical"
        >
          <div className="h-full w-px bg-border transition-colors group-hover:w-0.5 group-hover:bg-foreground/40" />
        </div>

        <div className="flex-1 overflow-y-auto">
          {detail.isError ? (
            <p className="p-6 text-sm text-red-500">Failed to load this issue.</p>
          ) : !issue ? (
            <p className="p-6 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-4 p-6">
              <h2
                id="flyout-title"
                className="text-lg font-semibold leading-tight"
                data-testid="flyout-title"
              >
                {issue.title}
              </h2>

              {issue.description && (
                <div className="text-muted-foreground">
                  <Markdown source={issue.description} />
                </div>
              )}

              <MetadataChips issue={issue} />

              <div>
                <div className="flex gap-1 border-b" role="tablist" aria-label="Issue detail">
                  {TABS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      id={`tab-${t}`}
                      role="tab"
                      aria-selected={tab === t}
                      aria-controls="issue-tabpanel"
                      data-testid={`tab-${t}`}
                      onClick={() => setTab(t)}
                      className={cn(
                        "border-b-2 px-3 py-1.5 text-sm capitalize",
                        tab === t
                          ? "border-foreground font-medium"
                          : "border-transparent text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <div
                  id="issue-tabpanel"
                  role="tabpanel"
                  aria-labelledby={`tab-${tab}`}
                  className="pt-3"
                  data-testid={`tabpanel-${tab}`}
                >
                  <Markdown
                    source={tab === "comments" ? issue.comments_md : issue.context_md}
                  />
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Run history
                </h3>
                {runs.isError ? (
                  <p className="text-xs text-red-500">Failed to load runs.</p>
                ) : (
                  <RunHistoryList runs={runs.data ?? []} />
                )}
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

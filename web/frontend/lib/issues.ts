// Issue-domain constants and helpers shared across the board UI.

// The five board states, in fixed display order (#012c spec). `dot` is the
// column/state accent colour.
export const STATES = [
  { key: "todo", label: "Todo", dot: "bg-slate-400" },
  { key: "in_review", label: "In Review", dot: "bg-amber-400" },
  { key: "running", label: "Running", dot: "bg-sky-400" },
  { key: "blocked", label: "Blocked", dot: "bg-red-400" },
  { key: "done", label: "Done", dot: "bg-emerald-400" },
] as const;

export type StateKey = (typeof STATES)[number]["key"];

// "30s ago" / "5m ago" / "2h ago" / "3d ago" from an ISO timestamp.
export function formatAge(iso: string | null): string {
  if (!iso) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

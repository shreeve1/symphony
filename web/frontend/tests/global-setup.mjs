import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Playwright globalSetup: build throwaway binding repos + a fixture
// bindings.yml so e2e file-write specs NEVER touch the live binding repos
// (/home/james/homelab, /home/james/trading/..., /home/james/symphony).
//
// The fixture mirrors the real bindings.yml entries (same names + metadata) but
// rewrites every repo_path to an absolute path under test-results/e2e-repos/.
// Both the API webServer (PODIUM_BINDINGS_PATH) and the runDbScript helpers
// (fixtures.ts) point at the file this writes, so all reads/writes stay isolated.
//
// It also guarantees a stable fixture-only "trading" binding: the mutating
// specs (board-dnd, archive, dashboard, reply) need a second board isolated
// from the homelab specs that share the persistent dev DB under fullyParallel.
// "trading" was a live binding until it was offboarded 2026-06-15, so we
// synthesize it here (a clone of a local binding) to keep the e2e suite
// decoupled from live binding churn.
//
// Generation runs in Python (via uv) so it reuses PyYAML — the frontend has no
// yaml dependency, and hand-parsing bindings.yml in JS would be brittle.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "../..");
const E2E_REPOS_ROOT = path.resolve(FRONTEND_ROOT, "test-results/e2e-repos");
const E2E_BINDINGS_PATH = path.resolve(
	FRONTEND_ROOT,
	"test-results/e2e-bindings.yml",
);

export default function globalSetup() {
	const script = `
import copy
import yaml
from pathlib import Path

real = Path(${JSON.stringify(path.resolve(REPO_ROOT, "bindings.yml"))})
repos_root = Path(${JSON.stringify(E2E_REPOS_ROOT)})
out = Path(${JSON.stringify(E2E_BINDINGS_PATH)})

data = yaml.safe_load(real.read_text(encoding="utf-8")) or {}
bindings = data.get("bindings") or []

# Guarantee a stable fixture-only "trading" board for the mutating specs.
# Clone a local (non-remote) live binding so all required config fields are
# present, prefer a coding binding (the original trading was coding, which the
# flyout's 7-chip layout asserts on — infra bindings add 3 more chips), then
# rename and force type=coding. Skip if a real "trading" binding ever returns.
if not any(str(b.get("name")) == "trading" for b in bindings):
    local = [b for b in bindings if "remote" not in b]
    if not local:
        raise SystemExit("global-setup: no local binding to clone for e2e 'trading' fixture")
    base = next((b for b in local if str(b.get("type")) == "coding"), local[0])
    fixture = copy.deepcopy(base)
    fixture["name"] = "trading"
    fixture["type"] = "coding"
    fixture.pop("remote", None)
    bindings.append(fixture)

for binding in bindings:
    name = str(binding["name"])
    repo = repos_root / name
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    # Seed a root file and a nested dir+file so the tree has something to expand
    # and a file to open/edit.
    (repo / "sample.md").write_text("# sample\\n", encoding="utf-8")
    (repo / "docs" / "note.md").write_text("nested\\n", encoding="utf-8")
    binding["repo_path"] = str(repo)

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(yaml.safe_dump({"bindings": bindings}, sort_keys=False), encoding="utf-8")
`;
	execFileSync("uv", ["run", "python", "-c", script], {
		cwd: REPO_ROOT,
		stdio: "inherit",
	});
}

// Allow running directly (`node tests/global-setup.mjs`) so the API webServer
// command can generate the fixture BEFORE uvicorn starts — Playwright runs
// webServers before globalSetup, so the file must exist by then.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
	globalSetup();
}

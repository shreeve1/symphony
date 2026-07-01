import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Playwright globalSetup: build throwaway binding repos + a fixture
// bindings.yml so e2e file-write specs NEVER touch the live binding repos
// (/home/james/homelab, /home/james/dotfiles, /home/james/symphony).
//
// The fixture mirrors the real bindings.yml entries (same names + metadata) but
// rewrites every repo_path to an absolute path under test-results/e2e-repos/.
// Both the API webServer (PODIUM_BINDINGS_PATH) and the runDbScript helpers
// (fixtures.ts) point at the file this writes, so all reads/writes stay isolated.
//
// Two-board isolation: non-mutating specs use the homelab board, mutating specs
// (board-dnd, archive, reply, flyout-tabs, schedule, …) use the dotfiles board.
// Both are real local coding bindings, isolated by name in the shared e2e DB.
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
import yaml
from pathlib import Path

real = Path(${JSON.stringify(path.resolve(REPO_ROOT, "bindings.yml"))})
repos_root = Path(${JSON.stringify(E2E_REPOS_ROOT)})
out = Path(${JSON.stringify(E2E_BINDINGS_PATH)})

data = yaml.safe_load(real.read_text(encoding="utf-8")) or {}
bindings = data.get("bindings") or []

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

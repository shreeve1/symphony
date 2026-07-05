import { execFileSync } from "node:child_process";
import path from "node:path";
import {
	test as base,
	expect,
	type ConsoleMessage,
	type Page,
} from "@playwright/test";

// Collected browser-side problems for one page: console.error lines, uncaught
// exceptions (pageerror), and failed network requests. Specs read this and
// assert it's empty after the page has settled.
export interface PageProblems {
	errors: string[];
}

// console noise that is not a real app fault. Extend per-test via
// expectCleanConsole(problems, { ignore: [/.../] }) rather than widening this.
const DEFAULT_IGNORE: RegExp[] = [
	/favicon\.ico/i, // Next dev serves no favicon; browser logs a 404 for it
	/[?&]_rsc=/, // App Router RSC prefetch: aborts on supersede + dev cold-compile 500s
	/net::ERR_ABORTED/, // navigation/reload cancels in-flight polling requests
];

export async function authenticate(page: Page) {
	const response = await page.request.post("/api/auth/login", {
		data: { password: "secret" },
	});
	expect(response.ok()).toBeTruthy();
}

export const test = base.extend<{
	problems: PageProblems;
	authenticated: void;
}>({
	authenticated: [
		async ({ page }, use) => {
			await authenticate(page);
			await use();
		},
		{ auto: true },
	],
	problems: [
		async ({ page }, use) => {
			const errors: string[] = [];

			page.on("console", (msg: ConsoleMessage) => {
				if (msg.type() === "error") {
					errors.push(`console.error: ${msg.text()}`);
				}
			});
			page.on("pageerror", (err) => {
				errors.push(`pageerror: ${err.message}`);
			});
			page.on("requestfailed", (req) => {
				const failure = req.failure()?.errorText ?? "unknown";
				errors.push(`requestfailed: ${req.method()} ${req.url()} (${failure})`);
			});
			page.on("response", (res) => {
				if (res.status() >= 400) {
					errors.push(
						`httperror: ${res.status()} ${res.request().method()} ${res.url()}`,
					);
				}
			});

			await use({ errors });
		},
		{ auto: true },
	],
});

export { expect };

const E2E_DB_PATH = path.resolve(__dirname, "../test-results/podium-e2e.db");
const E2E_PI_SESSION_DIR = path.resolve(
	__dirname,
	"../test-results/pi-sessions",
);
// Same fixture bindings.yml the API webServer + global-setup use (see
// playwright.config.ts). Helper subprocesses must read the throwaway repo paths
// from here, not the live bindings.yml, or session-tail writes land in a real repo.
const E2E_BINDINGS_PATH = path.resolve(
	__dirname,
	"../test-results/e2e-bindings.yml",
);

function runDbScript<T>(script: string): T {
	const stdout = execFileSync("uv", ["run", "python", "-c", script], {
		cwd: path.resolve(__dirname, "../../.."),
		env: {
			...process.env,
			PODIUM_DB_PATH: E2E_DB_PATH,
			PI_CODING_AGENT_SESSION_DIR: E2E_PI_SESSION_DIR,
			PODIUM_BINDINGS_PATH: E2E_BINDINGS_PATH,
		},
		stdio: "pipe",
	});
	return JSON.parse(stdout.toString() || "null") as T;
}

export function seedSkills(skills: { name: string; description?: string }[]) {
	const script = `
import json
from web.api.db import connect
from web.cli.podium_skills import ensure_schema
skills = ${JSON.stringify(skills)}
with connect() as connection:
    ensure_schema(connection)
    connection.executemany(
        "INSERT INTO skill(name, description, source) VALUES (?, ?, 'e2e') "
        "ON CONFLICT(name) DO UPDATE SET description = excluded.description, source = excluded.source",
        [(skill["name"], skill.get("description", "")) for skill in skills],
    )
    connection.commit()
print(json.dumps(True))
`;
	runDbScript<boolean>(script);
}

export function seedIssue(binding: string, title: string, state = "todo") {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
binding = ${JSON.stringify(binding)}
title = ${JSON.stringify(title)}
state = ${JSON.stringify(state)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          reasoning_effort, base_branch, comments_md, context_md,
          created_at, updated_at, last_event_at
        ) VALUES (?, ?, ?, ?, 'med', 'pi', 'high', 'main', '', '', ?, ?, ?)
        """,
        (binding, title, f"E2E polling fixture for {binding}.", state, now, now, now),
    )
    connection.commit()
    print(json.dumps({"issueId": cursor.lastrowid}))
`;
	return runDbScript<{ issueId: number }>(script);
}

export function seedWorktreeIssue(
	binding: string,
	title: string,
	state = "todo",
) {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
binding = ${JSON.stringify(binding)}
title = ${JSON.stringify(title)}
state = ${JSON.stringify(state)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          reasoning_effort, worktree_active, base_branch, comments_md, context_md,
          created_at, updated_at, last_event_at
        ) VALUES (?, ?, ?, ?, 'med', 'pi', 'high', TRUE, 'main', '', '', ?, ?, ?)
        """,
        (binding, title, f"E2E worktree fixture for {binding}.", state, now, now, now),
    )
    connection.commit()
    print(json.dumps({"issueId": cursor.lastrowid}))
`;
	return runDbScript<{ issueId: number }>(script);
}

export function setIssueComments(issueId: number, commentsMd: string) {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
issue_id = ${issueId}
comments = ${JSON.stringify(commentsMd)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    connection.execute(
        "UPDATE issue SET comments_md = ?, updated_at = ?, last_event_at = ? WHERE id = ?",
        (comments, now, now, issue_id),
    )
    connection.commit()
print(json.dumps(True))
`;
	runDbScript<boolean>(script);
}

export function updateIssueState(issueId: number, state: string) {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
issue_id = ${issueId}
state = ${JSON.stringify(state)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    connection.execute(
        "UPDATE issue SET state = ?, updated_at = ?, last_event_at = ? WHERE id = ?",
        (state, now, now, issue_id),
    )
    connection.commit()
print(json.dumps(True))
`;
	runDbScript<boolean>(script);
}

export function seedRunningRunIssue(
	binding: string,
	title: string,
	agent = "pi",
) {
	const script = `
import json
from datetime import UTC, datetime
from pathlib import Path
from web.api.db import connect
binding = ${JSON.stringify(binding)}
title = ${JSON.stringify(title)}
agent = ${JSON.stringify(agent)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
log_dir = Path(${JSON.stringify(path.resolve(__dirname, "../test-results"))})
log_dir.mkdir(parents=True, exist_ok=True)
with connect() as connection:
    issue_cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          reasoning_effort, base_branch, comments_md, context_md,
          created_at, updated_at, last_event_at
        ) VALUES (?, ?, ?, 'running', 'med', ?, 'high', 'main', '', '', ?, ?, ?)
        """,
        (binding, title, f"E2E running run fixture for {binding}.", agent, now, now, now),
    )
    issue_id = issue_cursor.lastrowid
    run_cursor = connection.execute(
        """
        INSERT INTO run(
          issue_id, agent, provider, model, state, verdict, summary, exit_code,
          cost_usd, input_tokens, output_tokens, branch_name,
          base_branch, log_path, skill_invoked, started_at, ended_at
        ) VALUES (?, ?, 'e2e', 'glm-5.1:high', 'running', NULL, NULL, NULL,
          NULL, NULL, NULL, NULL, NULL, 'main', NULL, NULL, ?, NULL)
        """,
        (issue_id, agent, now),
    )
    run_id = run_cursor.lastrowid
    log_path = log_dir / f"polling-run-{run_id}.log"
    connection.execute("UPDATE run SET log_path = ? WHERE id = ?", (str(log_path), run_id))
    connection.execute(
        """
        UPDATE issue
        SET latest_run_id = ?, latest_run_state = 'running', latest_verdict = NULL
        WHERE id = ?
        """,
        (run_id, issue_id),
    )
    connection.commit()
    print(json.dumps({"issueId": issue_id, "runId": run_id, "logPath": str(log_path)}))
`;
	return runDbScript<{ issueId: number; runId: number; logPath: string }>(
		script,
	);
}

// Issue with both preferred_agent and preferred_model left NULL but a finished
// run on record — the flyout should surface what that run actually used.
export function seedResolvedDispatchIssue(
	binding: string,
	title: string,
	agent = "pi",
	model = "deepseek-v4-pro:high",
) {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
binding = ${JSON.stringify(binding)}
title = ${JSON.stringify(title)}
agent = ${JSON.stringify(agent)}
model = ${JSON.stringify(model)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    issue_cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority,
          reasoning_effort, base_branch, comments_md, context_md,
          created_at, updated_at, last_event_at
        ) VALUES (?, ?, ?, 'in_review', 'med', 'high', 'main', '', '', ?, ?, ?)
        """,
        (binding, title, f"E2E resolved-dispatch fixture for {binding}.", now, now, now),
    )
    issue_id = issue_cursor.lastrowid
    run_cursor = connection.execute(
        """
        INSERT INTO run(
          issue_id, agent, provider, model, state, verdict, summary, exit_code,
          cost_usd, input_tokens, output_tokens, branch_name,
          base_branch, log_path, skill_invoked, started_at, ended_at
        ) VALUES (?, ?, 'openai', ?, 'succeeded', 'review', NULL, NULL,
          NULL, NULL, NULL, NULL, 'main', NULL, NULL, ?, ?)
        """,
        (issue_id, agent, model, now, now),
    )
    run_id = run_cursor.lastrowid
    connection.execute(
        """
        UPDATE issue
        SET latest_run_id = ?, latest_run_state = 'succeeded', latest_verdict = 'review'
        WHERE id = ?
        """,
        (run_id, issue_id),
    )
    connection.commit()
    print(json.dumps({"issueId": issue_id, "runId": run_id}))
`;
	return runDbScript<{ issueId: number; runId: number }>(script);
}

export function appendSessionTail(issueId: number, line: unknown) {
	const script = `
import json
import os
import yaml
from pathlib import Path
from session_continuity import derive_session_id, session_file_path
from web.api.db import connect
issue_id = ${issueId}
line = ${JSON.stringify(line)}
with connect() as connection:
    row = connection.execute(
        """
        SELECT i.binding_name, r.agent
        FROM issue i
        INNER JOIN run r ON r.id = i.latest_run_id
        WHERE i.id = ?
        """,
        (issue_id,),
    ).fetchone()
    binding = row["binding_name"]
    agent = row["agent"]
raw_bindings = yaml.safe_load(Path(os.environ.get("PODIUM_BINDINGS_PATH", "bindings.yml")).read_text())
repo_path = next(
    item["repo_path"]
    for item in raw_bindings["bindings"]
    if item["name"] == binding
)
session_id = derive_session_id(issue_id)
path = session_file_path(agent, repo_path, session_id)
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(line) + "\\n")
print(json.dumps({"path": str(path)}))
`;
	return runDbScript<{ path: string }>(script);
}

export function finishRun(runId: number, logText: string) {
	const script = `
import json
from datetime import UTC, datetime
from pathlib import Path
from web.api.db import connect
run_id = ${runId}
log_text = ${JSON.stringify(logText)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    row = connection.execute("SELECT issue_id, log_path FROM run WHERE id = ?", (run_id,)).fetchone()
    path = Path(row["log_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(log_text, encoding="utf-8")
    connection.execute(
        """
        UPDATE run
        SET state = 'succeeded', verdict = 'review', summary = 'E2E polling finished',
            exit_code = 0, ended_at = ?
        WHERE id = ?
        """,
        (now, run_id),
    )
    connection.execute(
        """
        UPDATE issue
        SET state = 'in_review', latest_run_state = 'succeeded', latest_verdict = 'review',
            updated_at = ?, last_event_at = ?
        WHERE id = ?
        """,
        (now, now, row["issue_id"]),
    )
    connection.commit()
print(json.dumps(True))
`;
	runDbScript<boolean>(script);
}

export function finishRunWithIssueComment(runId: number, comment: string) {
	const script = `
import json
from datetime import UTC, datetime
from web.api.db import connect
run_id = ${runId}
comment = ${JSON.stringify(comment)}
now = datetime.now(UTC).replace(microsecond=0).isoformat()
with connect() as connection:
    row = connection.execute("SELECT issue_id FROM run WHERE id = ?", (run_id,)).fetchone()
    connection.execute(
        """
        UPDATE run
        SET state = 'succeeded', verdict = 'review', summary = 'E2E polling finished',
            exit_code = 0, ended_at = ?
        WHERE id = ?
        """,
        (now, run_id),
    )
    connection.execute(
        """
        UPDATE issue
        SET state = 'in_review', latest_run_state = 'succeeded', latest_verdict = 'review',
            comments_md = COALESCE(comments_md, '') || ?, updated_at = ?, last_event_at = ?
        WHERE id = ?
        """,
        ("\\n\\n" + comment.strip(), now, now, row["issue_id"]),
    )
    connection.commit()
print(json.dumps(True))
`;
	runDbScript<boolean>(script);
}

export function expectCleanConsole(
	problems: PageProblems,
	options: { ignore?: RegExp[] } = {},
) {
	const ignore = [...DEFAULT_IGNORE, ...(options.ignore ?? [])];
	const real = problems.errors.filter(
		(line) => !ignore.some((rx) => rx.test(line)),
	);
	expect(
		real,
		`unexpected browser console problems:\n${real.join("\n")}`,
	).toEqual([]);
}

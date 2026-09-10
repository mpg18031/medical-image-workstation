import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(E2E_DIR, "../..");
const STATE_FILE = resolve(E2E_DIR, "../test-results/stack-state.json");
const COMPOSE_FILES = [
  "-f",
  "infra/docker-compose.yml",
  "-f",
  "infra/docker-compose.e2e.yml",
];

export default async function globalTeardown(): Promise<void> {
  if (!existsSync(STATE_FILE)) return;

  const state = JSON.parse(readFileSync(STATE_FILE, "utf8")) as {
    apiPid?: number;
    project: string;
  };

  if (state.apiPid) {
    try {
      process.kill(state.apiPid, "SIGTERM");
    } catch {
      // Already exited.
    }
  }

  // -v removes the volumes too: E2E state must never leak into the next run.
  execFileSync(
    "docker",
    ["compose", ...COMPOSE_FILES, "-p", state.project, "down", "-v"],
    { cwd: REPO_ROOT, stdio: "inherit" },
  );

  rmSync(STATE_FILE, { force: true });
}

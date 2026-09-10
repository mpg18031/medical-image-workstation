import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { FullConfig } from "@playwright/test";

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(E2E_DIR, "../..");
const STATE_FILE = resolve(E2E_DIR, "../test-results/stack-state.json");

/**
 * Brings up a disposable stack for E2E: PostgreSQL, MinIO, a mock IdP and the
 * API. Always synthetic data; the suite never touches a real PACS.
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  const compose = [
    "compose",
    "-f",
    "infra/docker-compose.yml",
    "-f",
    "infra/docker-compose.e2e.yml",
    "-p",
    "mivw-e2e",
  ];
  const e2eEnv = {
    ...process.env,
    MIVW_MODE: "local",
    MIVW_E2E: "1",
    MIVW_API_ORIGIN: "http://127.0.0.1:8010",
    MIVW_ALLOWED_ORIGIN: "null",
    MIVW_DB_DSN:
      "postgresql://postgres:devonly_not_for_deployment@127.0.0.1:55434/mivw",
    MIVW_OBJECT_ENDPOINT: "http://127.0.0.1:59000",
    MIVW_OBJECT_BUCKET: "mivw-volumes",
    AWS_ACCESS_KEY_ID: "mivwdev",
    AWS_SECRET_ACCESS_KEY: "devonly_not_for_deployment",
    MIVW_OIDC_ISSUER: "http://localhost:58080/realms/mivw",
    MIVW_OIDC_AUDIENCE: "mivw-workstation",
    MIVW_ENCRYPTION_KEY_ID: "mivw-phi-v1",
    MIVW_HMAC_KEY_ID: "mivw-hmac-v1",
    MIVW_KEY_MATERIAL_MIVW_PHI_V1: "development-only-encryption-key",
    MIVW_KEY_MATERIAL_MIVW_HMAC_V1: "development-only-hmac-key",
  };

  run("docker", [...compose, "up", "-d", "--wait"]);
  run(".venv/bin/python", ["scripts/migrate.py", "apply"], e2eEnv);
  run(".venv/bin/python", ["scripts/migrate.py", "seed"], e2eEnv);
  mkdirSync(resolve(E2E_DIR, "../test-results"), { recursive: true });

  const api = spawn(
    ".venv/bin/uvicorn",
    [
      "mivw_api.main:create_app",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      "8010",
    ],
    {
      cwd: REPO_ROOT,
      env: { ...e2eEnv, MIVW_E2E: "1" },
      stdio: "ignore",
      detached: true,
    },
  );
  api.unref();

  await waitForHealth("http://127.0.0.1:8010/healthz", 60_000);

  run("npm", ["run", "build"], e2eEnv, resolve(REPO_ROOT, "desktop"));

  writeFileSync(
    STATE_FILE,
    JSON.stringify({ apiPid: api.pid, project: "mivw-e2e" }),
  );
}

function run(
  command: string,
  args: string[],
  env = process.env,
  cwd = REPO_ROOT,
): void {
  execFileSync(command, args, { cwd, stdio: "inherit", env });
}

async function waitForHealth(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return;
    } catch {
      // Not up yet.
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`API did not become healthy within ${timeoutMs}ms: ${url}`);
}

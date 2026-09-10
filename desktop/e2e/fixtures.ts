import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from "@playwright/test";
import { pathToFileURL } from "node:url";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const APP_URL = pathToFileURL(
  path.resolve("dist/electron/UnPackaged/index.html"),
).toString();

/**
 * Launches the packaged app and clears the research-use gate.
 *
 * Every journey starts here, because the gate is deliberately unskippable.
 */
export async function launchApp(
  env: Record<string, string> = {},
): Promise<{ app: ElectronApplication; window: Page }> {
  const app = await electron.launch({
    args: [
      `--user-data-dir=${mkdtempSync(path.join(tmpdir(), "mivw-e2e-"))}`,
      "dist/electron/UnPackaged/electron-main.js",
    ],
    env: {
      ...process.env,
      APP_URL,
      MIVW_API_ORIGIN: "http://127.0.0.1:8010",
      MIVW_OIDC_ISSUER: "http://localhost:58080/realms/mivw",
      MIVW_MODE: "local",
      MIVW_E2E: "1",
      ...env,
    },
  });

  const window = await app.firstWindow();
  await window.waitForLoadState("domcontentloaded");
  return { app, window };
}

export async function acknowledgeResearchUse(window: Page): Promise<void> {
  const dialog = window.getByRole("dialog", { name: /research use only/i });
  await expect(dialog).toBeVisible();

  await window.getByTestId("ruo-confirm").click();
  await window.getByTestId("ruo-acknowledge").click();
  await expect(dialog).toBeHidden();
}

export async function openFirstStudy(window: Page): Promise<void> {
  const table = window.getByTestId("study-table");
  await expect(table).toBeVisible();
  await table.getByRole("row").nth(1).click();
}

export { expect, test };

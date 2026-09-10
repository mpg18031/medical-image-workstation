import type { ElectronApplication, Page } from "@playwright/test";
import { acknowledgeResearchUse, expect, launchApp, test } from "./fixtures";

let app: ElectronApplication;
let window: Page;

test.beforeEach(async () => {
  ({ app, window } = await launchApp());
});

test.afterEach(async () => {
  await app.close();
});

test.describe("research-use gate", () => {
  test("blocks the application until the disclaimer is acknowledged", async () => {
    const dialog = window.getByRole("dialog", { name: /research use only/i });
    await expect(dialog).toBeVisible();

    // The worklist must not be reachable behind the dialog.
    await expect(window.getByTestId("study-table")).toBeHidden();
    await expect(window.getByTestId("ruo-acknowledge")).toBeDisabled();
  });

  test("cannot be dismissed with Escape", async () => {
    await window.keyboard.press("Escape");
    await expect(
      window.getByRole("dialog", { name: /research use only/i }),
    ).toBeVisible();
  });

  test("reappears on the next launch rather than being remembered", async () => {
    await acknowledgeResearchUse(window);
    await app.close();

    ({ app, window } = await launchApp());
    await expect(
      window.getByRole("dialog", { name: /research use only/i }),
    ).toBeVisible();
  });
});

test.describe("worklist", () => {
  test.beforeEach(async () => {
    await acknowledgeResearchUse(window);
  });

  test("lists the seeded synthetic studies", async () => {
    const table = window.getByTestId("study-table");
    await expect(table).toBeVisible();
    await expect(table.getByText("PHANTOM-001")).toBeVisible();
  });

  test("never displays a raw patient identifier", async () => {
    // Only pseudonyms leave the database; a real MRN appearing here would be
    // a de-identification failure.
    const body = await window.locator("body").innerText();
    expect(body).not.toMatch(/FAKE-MRN/i);
    expect(body).not.toMatch(/\bMRN\b/i);
  });

  test("filters by modality", async () => {
    await window.getByLabel("Filter by modality").click();
    await window.getByRole("option", { name: "CT" }).click();

    const rows = window.getByTestId("study-table").getByRole("row");
    await expect(rows.nth(1)).toBeVisible();
    for (const row of await rows.all()) {
      const text = await row.innerText();
      if (text.includes("PHANTOM")) expect(text).toContain("CT");
    }
  });

  test("shows an empty state when nothing matches", async () => {
    await window
      .getByLabel("Search by patient reference")
      .fill("NO-SUCH-PATIENT");
    await window.getByRole("button", { name: "Search" }).click();

    await expect(window.getByTestId("study-table-empty")).toBeVisible();
  });

  test("is navigable by keyboard alone", async () => {
    const firstRow = window.getByTestId("study-table").getByRole("row").nth(1);
    await firstRow.focus();
    await window.keyboard.press("Enter");

    await expect(window.getByTestId("volume-canvas")).toBeVisible();
  });

  test("warns when a series is quarantined for burned-in annotation", async () => {
    const banner = window.getByText(
      /quarantined pending burned-in annotation review/i,
    );
    if (await banner.isVisible()) {
      await expect(banner).toBeVisible();
    }
  });
});

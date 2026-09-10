import type { ElectronApplication, Page } from "@playwright/test";
import {
  acknowledgeResearchUse,
  expect,
  launchApp,
  openFirstStudy,
  test,
} from "./fixtures";

let app: ElectronApplication;
let window: Page;

async function drawMeasurement(page: Page): Promise<void> {
  await page.getByRole("button", { name: /measure/i }).click();

  const canvas = page.getByTestId("volume-canvas");
  const box = (await canvas.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.5);
  await page.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.5);
}

test.afterEach(async () => {
  await app.close();
});

test.describe("annotations", () => {
  test.beforeEach(async () => {
    ({ app, window } = await launchApp());
    await acknowledgeResearchUse(window);
    await openFirstStudy(window);
  });

  test("records a measurement in millimetres", async () => {
    await drawMeasurement(window);

    const list = window.getByRole("listitem").filter({ hasText: "mm" });
    await expect(list.first()).toBeVisible({ timeout: 15_000 });
    await expect(list.first()).toContainText(/\d+\.\d mm/);
  });

  test("persists a measurement across an application restart", async () => {
    await drawMeasurement(window);
    const before = await window
      .getByRole("listitem")
      .filter({ hasText: "mm" })
      .first()
      .innerText();

    await app.close();
    ({ app, window } = await launchApp());
    await acknowledgeResearchUse(window);
    await openFirstStudy(window);

    // Geometry is stored in patient coordinates, so the value must be
    // identical, not merely present.
    const after = await window
      .getByRole("listitem")
      .filter({ hasText: "mm" })
      .first()
      .innerText();
    expect(after).toBe(before);
  });
});

test.describe("permissions", () => {
  test("a viewer cannot create an annotation", async () => {
    ({ app, window } = await launchApp({ MIVW_E2E_ROLE: "viewer" }));
    await acknowledgeResearchUse(window);
    await openFirstStudy(window);

    await expect(
      window.getByRole("button", { name: /measure/i }),
    ).toBeDisabled();
  });

  test("a viewer cannot start an inference run", async () => {
    ({ app, window } = await launchApp({ MIVW_E2E_ROLE: "viewer" }));
    await acknowledgeResearchUse(window);
    await openFirstStudy(window);

    await expect(window.getByTestId("run-model")).toBeDisabled();
  });

  test("a viewer cannot reach the model registry", async () => {
    ({ app, window } = await launchApp({ MIVW_E2E_ROLE: "viewer" }));
    await acknowledgeResearchUse(window);

    await expect(window.getByRole("link", { name: "Models" })).toHaveCount(0);
  });

  test("an admin can reach the model registry", async () => {
    ({ app, window } = await launchApp({ MIVW_E2E_ROLE: "admin" }));
    await acknowledgeResearchUse(window);

    await window.getByRole("link", { name: "Models" }).click();
    await expect(
      window.getByRole("heading", { name: /model registry/i }),
    ).toBeVisible();
  });
});

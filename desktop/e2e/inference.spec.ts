import {
  acknowledgeResearchUse,
  expect,
  launchApp,
  test,
  type ElectronApplication,
  type Page,
} from "./fixtures";

let app: ElectronApplication;
let window: Page;

test.beforeEach(async () => {
  ({ app, window } = await launchApp());
});

test.afterEach(async () => {
  await app.close();
});

test.describe("AI inference", () => {
  test("researcher can select a registered model for the current volume", async () => {
    const win = window;
    // Research-use gate must be acknowledged before anything else is reachable.
    await acknowledgeResearchUse(win);

    await win.getByRole("row", { name: /PHANTOM-001/ }).click();
    await win.getByLabel("Model").click();
    await win.getByRole("option", { name: "liver-seg 1.4.0" }).click();
    await expect(win.getByRole("button", { name: "Run model" })).toBeEnabled();
  });

  test("a model whose input spec does not match the volume is rejected clearly", async () => {
    const win = window;
    await acknowledgeResearchUse(win);

    await win.getByRole("row", { name: /PHANTOM-ANISOTROPIC/ }).click();
    await win.getByLabel("Model").click();
    await win.getByRole("option", { name: "liver-seg 1.4.0" }).click();
    await expect(win.getByRole("button", { name: "Run model" })).toBeEnabled();
    await win.getByRole("button", { name: "Run model" }).click();

    // Silent resampling would produce a plausible but wrong result, so the
    // failure must be explicit and explain the mismatch.
    const alert = win.getByRole("alert");
    await expect(alert).toContainText(/model requires/i);
    await expect(alert).toContainText(/spacing/i);
    await expect(win.getByTestId("segmentation-overlay")).toHaveCount(0);
  });

  test("a viewer cannot start an inference run", async () => {
    const win = window;
    await acknowledgeResearchUse(win);
    await win.getByTestId("e2e-switch-role").click();
    await win.getByRole("option", { name: "viewer" }).click();

    await win.getByRole("row", { name: /PHANTOM-001/ }).click();
    await expect(win.getByRole("button", { name: "Run model" })).toBeDisabled();
  });
});

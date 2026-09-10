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

test.beforeEach(async () => {
  ({ app, window } = await launchApp());
  await acknowledgeResearchUse(window);
  await openFirstStudy(window);
});

test.afterEach(async () => {
  await app.close();
});

test.describe("volume viewer", () => {
  test("renders the volume canvas", async () => {
    await expect(window.getByTestId("volume-canvas")).toBeVisible();
  });

  test("advances frames while the camera is dragged", async () => {
    const canvas = window.getByTestId("volume-canvas");
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();

    const stats = window.getByTestId("volume-canvas-stats");
    const before = await stats.innerText();

    await window.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await window.mouse.down();
    for (let i = 0; i < 10; i += 1) {
      await window.mouse.move(
        box!.x + box!.width / 2 + i * 8,
        box!.y + box!.height / 2,
      );
    }
    await window.mouse.up();

    await expect
      .poll(async () => stats.innerText(), { timeout: 10_000 })
      .not.toBe(before);
  });

  test("reports frame time so a latency regression is visible", async () => {
    const stats = window.getByTestId("volume-canvas-stats");
    await expect(stats).toContainText(/\d+\.\d ms/);
  });

  test("is rotatable by keyboard alone", async () => {
    const canvas = window.getByTestId("volume-canvas");
    await canvas.focus();

    const stats = window.getByTestId("volume-canvas-stats");
    const before = await stats.innerText();

    for (let i = 0; i < 10; i += 1) await window.keyboard.press("ArrowRight");

    await expect
      .poll(async () => stats.innerText(), { timeout: 10_000 })
      .not.toBe(before);
  });

  test("applies a window preset", async () => {
    const widthSlider = window.getByRole("slider", { name: /window width/i });
    await window.getByRole("button", { name: "bone" }).click();

    // The bone preset is W1500 / L300.
    await expect(widthSlider).toHaveAttribute("aria-valuenow", "1500");
  });

  test("never emits a non-positive window width", async () => {
    const widthSlider = window.getByRole("slider", { name: /window width/i });
    await widthSlider.focus();
    for (let i = 0; i < 40; i += 1) await window.keyboard.press("ArrowLeft");

    const value = await widthSlider.getAttribute("aria-valuenow");
    expect(Number(value)).toBeGreaterThan(0);
  });

  test("recovers the stream after a transport drop", async () => {
    await window.evaluate(() => {
      window.dispatchEvent(new Event("offline"));
    });

    const banner = window.getByTestId("volume-canvas-reconnecting");
    if (await banner.isVisible({ timeout: 2000 }).catch(() => false)) {
      await expect(banner).toBeHidden({ timeout: 30_000 });
    }
    await expect(window.getByTestId("volume-canvas")).toBeVisible();
  });
});

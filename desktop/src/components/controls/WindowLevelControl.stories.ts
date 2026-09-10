import type { Meta, StoryObj } from "@storybook/vue3";
import { expect, fn, within } from "@storybook/test";
import WindowLevelControl from "./WindowLevelControl.vue";

const meta: Meta<typeof WindowLevelControl> = {
  title: "Controls/WindowLevelControl",
  component: WindowLevelControl,
  args: { center: 40, width: 400, onChange: fn() },
  parameters: { a11y: { test: "error" } },
};

export default meta;
type Story = StoryObj<typeof WindowLevelControl>;

/**
 * Quasar's slider reads the legacy `keyCode`, which `userEvent.keyboard` no
 * longer sets. Dispatching the event directly is what a real key press
 * produces, so this still exercises genuine keyboard operability.
 */
const KEY_CODES: Record<string, number> = {
  ArrowLeft: 37,
  ArrowRight: 39,
  ArrowUp: 38,
  ArrowDown: 40,
};

function pressKey(element: HTMLElement, key: string, times = 1): void {
  for (let i = 0; i < times; i += 1) {
    element.dispatchEvent(
      new KeyboardEvent("keydown", {
        key,
        code: key,
        keyCode: KEY_CODES[key],
        bubbles: true,
      }),
    );
  }
}

function widthSlider(canvasElement: HTMLElement): HTMLElement {
  return within(canvasElement).getByRole("slider", { name: /window width/i });
}

export const SoftTissue: Story = {};

export const Lung: Story = {
  args: { center: -600, width: 1500 },
};

export const Bone: Story = {
  args: { center: 300, width: 1500 },
};

export const Disabled: Story = {
  args: { disabled: true },
  play: async ({ canvasElement, args }) => {
    pressKey(widthSlider(canvasElement), "ArrowRight", 3);
    await expect(args.onChange).not.toHaveBeenCalled();
  },
};

export const KeyboardAdjustable: Story = {
  name: "Adjustable by keyboard alone",
  play: async ({ canvasElement, args }) => {
    const slider = widthSlider(canvasElement);

    slider.focus();
    pressKey(slider, "ArrowRight", 10);

    // A clinical tool must be fully operable without a mouse.
    await expect(args.onChange).toHaveBeenCalledTimes(10);
    await expect(args.onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ width: 410 }),
    );
  },
};

export const RejectsNonPositiveWidth: Story = {
  name: "Never emits a width at or below zero",
  args: { width: 3 },
  play: async ({ canvasElement, args }) => {
    const slider = widthSlider(canvasElement);

    slider.focus();
    pressKey(slider, "ArrowLeft", 8);

    // A non-positive width divides by zero in the shader's window transform.
    const calls = (args.onChange as ReturnType<typeof fn>).mock.calls;
    await expect(calls.length).toBeGreaterThan(0);
    for (const [payload] of calls) {
      await expect(payload.width).toBeGreaterThan(0);
    }
  },
};

export const AnnouncesValuesToScreenReaders: Story = {
  play: async ({ canvasElement }) => {
    const slider = widthSlider(canvasElement);
    await expect(slider).toHaveAttribute("aria-valuenow", "400");
    await expect(slider).toHaveAttribute(
      "aria-valuetext",
      "400 Hounsfield units",
    );
  },
};

export const IsReachableByTab: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    for (const name of [/window center/i, /window width/i]) {
      await expect(canvas.getByRole("slider", { name })).toHaveAttribute(
        "tabindex",
        "0",
      );
    }
  },
};

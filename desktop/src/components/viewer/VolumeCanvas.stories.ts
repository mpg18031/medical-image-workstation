import type { Meta, StoryObj } from "@storybook/vue3";
import { expect, fn, userEvent, within } from "@storybook/test";
import VolumeCanvas from "./VolumeCanvas.vue";

const meta: Meta<typeof VolumeCanvas> = {
  title: "Viewer/VolumeCanvas",
  component: VolumeCanvas,
  args: {
    frame: null,
    width: 512,
    height: 512,
    frameTimeMs: 8.4,
    droppedFrames: 0,
    onOrbit: fn(),
    onZoom: fn(),
    onWindowLevel: fn(),
  },
  parameters: { a11y: { test: "error" } },
};

export default meta;
type Story = StoryObj<typeof VolumeCanvas>;

export const WithinLatencyBudget: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("volume-canvas-stats")).toHaveTextContent(
      "8.4 ms",
    );
  },
};

export const ExceedingLatencyBudget: Story = {
  args: { frameTimeMs: 27.3, droppedFrames: 14 },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stats = canvas.getByTestId("volume-canvas-stats");
    // Over the 16 ms budget the reading is warned, not silently accepted.
    await expect(stats).toHaveTextContent("27.3 ms");
    await expect(stats).toHaveTextContent("14 dropped");
  },
};

export const Reconnecting: Story = {
  args: { connectionState: "reconnecting" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByTestId("volume-canvas-reconnecting"),
    ).toBeVisible();
    await expect(canvas.getByRole("status")).toHaveTextContent(/reconnecting/i);
  },
};

export const OverlayHidden: Story = {
  args: { showOverlay: false },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.queryByTestId("volume-canvas-stats"),
    ).not.toBeInTheDocument();
  },
};

export const RotatableByKeyboard: Story = {
  name: "Camera is controllable without a mouse",
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const surface = canvas.getByTestId("volume-canvas");

    surface.focus();
    await userEvent.keyboard("{ArrowRight}");

    await expect(args.onOrbit).toHaveBeenCalledWith(2, 0);
  },
};

export const ShiftAcceleratesRotation: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    canvas.getByTestId("volume-canvas").focus();
    await userEvent.keyboard("{Shift>}{ArrowLeft}{/Shift}");

    await expect(args.onOrbit).toHaveBeenCalledWith(-10, 0);
  },
};

export const ZoomableByKeyboard: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    canvas.getByTestId("volume-canvas").focus();
    await userEvent.keyboard("+");

    await expect(args.onZoom).toHaveBeenCalledWith(-1);
  },
};

export const DescribesItselfToScreenReaders: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const surface = canvas.getByRole("img");
    await expect(surface).toHaveAccessibleName(/arrow keys/i);
  },
};

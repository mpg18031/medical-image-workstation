import type { Meta, StoryObj } from "@storybook/vue3";
import { expect, fn, userEvent, within } from "@storybook/test";
import LabelLegend from "./LabelLegend.vue";

const labels = {
  "1": { name: "liver", color: "#d94f3d" },
  "2": { name: "tumour", color: "#4d9f94" },
  "3": { name: "vessel", color: "#7a5cc4" },
};

const meta: Meta<typeof LabelLegend> = {
  title: "Controls/LabelLegend",
  component: LabelLegend,
  args: {
    labels,
    visible: new Set([1, 2, 3]),
    onToggle: fn(),
    onShowAll: fn(),
  },
  parameters: { a11y: { test: "error" } },
};

export default meta;
type Story = StoryObj<typeof LabelLegend>;

export const Default: Story = {};

export const WithVolumes: Story = {
  args: {
    stats: {
      "1": { volumeMl: 1543.2 },
      "2": { volumeMl: 12.7 },
      "3": { volumeMl: 88.4 },
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText("1543.2 mL")).toBeVisible();
  },
};

export const Empty: Story = {
  args: { labels: {}, visible: new Set() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("label-legend-empty")).toBeVisible();
  },
};

export const PartiallyHidden: Story = {
  args: { visible: new Set([1]) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("label-show-all")).toBeEnabled();
  },
};

export const ShowAllDisabledWhenAllVisible: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("label-show-all")).toBeDisabled();
  },
};

export const TogglesALabel: Story = {
  args: { visible: new Set([1, 2, 3]) },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByLabelText("Show tumour"));

    await expect(args.onToggle).toHaveBeenCalledWith(2, false);
  },
};

export const EveryLabelHasATextName: Story = {
  name: "Colour is never the only cue",
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Roughly 1 in 12 men has a colour vision deficiency; a swatch alone is
    // not an acceptable identifier in a clinical tool.
    for (const name of ["liver", "tumour", "vessel"]) {
      await expect(canvas.getByText(name)).toBeVisible();
    }
  },
};

export const Disabled: Story = {
  args: { disabled: true },
};

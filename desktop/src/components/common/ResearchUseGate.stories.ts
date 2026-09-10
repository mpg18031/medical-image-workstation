import type { Meta, StoryObj } from "@storybook/vue3";
import { expect, fn, userEvent, within } from "@storybook/test";
import ResearchUseGate from "./ResearchUseGate.vue";

const meta: Meta<typeof ResearchUseGate> = {
  title: "Common/ResearchUseGate",
  component: ResearchUseGate,
  args: { modelValue: true, onAcknowledge: fn() },
  parameters: { a11y: { test: "error" } },
};

export default meta;
type Story = StoryObj<typeof ResearchUseGate>;

export const Default: Story = {};

export const CannotAcknowledgeWithoutConfirming: Story = {
  name: "Acknowledge stays disabled until the checkbox is ticked",
  play: async ({ canvasElement }) => {
    // The dialog renders in a portal, so query the whole document body.
    const screen = within(canvasElement.ownerDocument.body);
    const button = await screen.findByTestId("ruo-acknowledge");

    // A one-click dismiss would let users bypass the restriction reflexively.
    await expect(button).toBeDisabled();
  },
};

export const AcknowledgeAfterConfirming: Story = {
  play: async ({ canvasElement, args }) => {
    const screen = within(canvasElement.ownerDocument.body);

    await userEvent.click(await screen.findByTestId("ruo-confirm"));
    await userEvent.click(await screen.findByTestId("ruo-acknowledge"));

    await expect(args.onAcknowledge).toHaveBeenCalledOnce();
  },
};

export const StatesTheRegulatoryPosition: Story = {
  play: async ({ canvasElement }) => {
    const screen = within(canvasElement.ownerDocument.body);
    // The key phrase is split across a <strong>, so match on the dialog's
    // flattened text rather than a single element.
    const dialog = await screen.findByRole("dialog");
    const text = dialog.textContent?.replace(/\s+/g, " ") ?? "";

    await expect(text).toMatch(/not.*cleared or approved medical device/i);
    await expect(text).toMatch(/primary diagnosis/i);
  },
};

export const IsLabelledForScreenReaders: Story = {
  play: async ({ canvasElement }) => {
    const screen = within(canvasElement.ownerDocument.body);
    const dialog = await screen.findByRole("dialog");
    await expect(dialog).toHaveAttribute("aria-labelledby", "ruo-title");
  },
};

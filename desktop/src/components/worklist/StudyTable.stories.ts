import type { Meta, StoryObj } from "@storybook/vue3";
import { expect, fn, userEvent, within } from "@storybook/test";
import StudyTable from "./StudyTable.vue";
import type { StudySummary } from "src/services/types";

function study(
  id: string,
  overrides: Partial<StudySummary> = {},
): StudySummary {
  return {
    id,
    patient: {
      id: `p-${id}`,
      pseudonym: `PHANTOM-${id}`,
      birthYear: 1970,
      sex: "O",
    },
    studyDatetime: "2026-03-14T10:15:00Z",
    description: "Shepp-Logan phantom, isotropic",
    modalities: ["CT"],
    seriesCount: 2,
    ...overrides,
  };
}

const meta: Meta<typeof StudyTable> = {
  title: "Worklist/StudyTable",
  component: StudyTable,
  args: { studies: [study("001"), study("002")], onSelect: fn() },
  parameters: { a11y: { test: "error" } },
};

export default meta;
type Story = StoryObj<typeof StudyTable>;

export const Default: Story = {};

export const Loading: Story = {
  args: { studies: [], loading: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // A skeleton with no accessible status leaves screen-reader users guessing.
    await expect(canvas.getByRole("status")).toHaveTextContent(/loading/i);
  },
};

export const Empty: Story = {
  args: { studies: [] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("study-table-empty")).toBeVisible();
    await expect(canvas.queryByTestId("study-table")).not.toBeInTheDocument();
  },
};

export const ErrorState: Story = {
  args: { studies: [], error: "The service is temporarily unavailable." },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole("alert")).toHaveTextContent(
      /temporarily unavailable/i,
    );
  },
};

export const Selected: Story = {
  args: { selectedId: "002" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const rows = canvas.getAllByRole("row");
    const selected = rows.find(
      (r) => r.getAttribute("aria-selected") === "true",
    );
    await expect(selected).toHaveTextContent("PHANTOM-002");
  },
};

export const SelectableByKeyboard: Story = {
  name: "Rows are selectable without a mouse",
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const firstRow = canvas.getAllByRole("row")[1]!;

    firstRow.focus();
    await userEvent.keyboard("{Enter}");

    await expect(args.onSelect).toHaveBeenCalledWith("001");
  },
};

export const SpaceAlsoSelects: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    canvas.getAllByRole("row")[2]!.focus();
    await userEvent.keyboard(" ");

    await expect(args.onSelect).toHaveBeenCalledWith("002");
  },
};

export const MissingDatesRenderPlaceholder: Story = {
  args: { studies: [study("003", { studyDatetime: null, description: null })] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // An empty cell is ambiguous; an explicit dash reads as "absent".
    await expect(canvas.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  },
};

export const MultipleModalities: Story = {
  args: {
    studies: [study("004", { modalities: ["CT", "PT"], seriesCount: 6 })],
  },
};

import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Tag, TAG_TONES, TagList, type TagItem } from "./tag";

const CROPS: readonly TagItem[] = [
  { id: "cotton", label: "Cotton" },
  { id: "banana", label: "Banana" },
  { id: "sugarcane", label: "Sugarcane" },
  { id: "papaya", label: "Papaya" },
  { id: "pomegranate", label: "Pomegranate" },
];

const meta = {
  title: "Patterns/Tag",
  component: TagList,
  args: { items: CROPS, max: 2 },
} satisfies Meta<typeof TagList>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Extra tags collapse into "+N"; hover or focus it to read the rest. */
export const Overflow: Story = {};

export const AllVisible: Story = {
  args: { max: 5 },
};

export const NoTags: Story = {
  args: { items: [] },
};

export const LongLabel: Story = {
  args: {
    items: [{ id: "demo-plot", label: "Integrated nutrient management demonstration plot" }],
  },
};

/** The same label always gets the same tone, so a crop looks identical on every screen. */
export const Tones: Story = {
  render: () => (
    <ul className="flex flex-wrap gap-2">
      {TAG_TONES.map((tone) => (
        <li key={tone}>
          <Tag tone={tone}>{tone}</Tag>
        </li>
      ))}
    </ul>
  ),
};

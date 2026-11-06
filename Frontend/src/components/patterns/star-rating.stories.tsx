import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";

import { StarRating, StarRatingInput } from "./star-rating";

const WORDS: Readonly<Record<number, string>> = {
  1: "Very poor",
  2: "Poor",
  3: "Fair",
  4: "Good",
  5: "Very good",
};

const meta = {
  title: "Patterns/StarRating",
  component: StarRating,
  args: { score: 4, size: "sm" },
  argTypes: {
    score: { control: { type: "range", min: 1, max: 5, step: 1 } },
    size: { control: "select", options: ["xs", "sm", "md"] },
  },
} satisfies Meta<typeof StarRating>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const EveryScore: Story = {
  render: (args) => (
    <ul className="flex flex-col gap-2">
      {[1, 2, 3, 4, 5].map((score) => (
        <li key={score}>
          <StarRating {...args} score={score} />
        </li>
      ))}
    </ul>
  ),
};

function InputDemo({ invalid = false }: { invalid?: boolean }): React.JSX.Element {
  const [value, setValue] = useState<number | null>(null);
  return (
    <StarRatingInput
      legend="How was the installation?"
      value={value}
      onValueChange={setValue}
      describe={(score) => WORDS[score] ?? ""}
      invalid={invalid ? value === null : false}
    />
  );
}

/** Choosing stars, with the words for each score. */
export const Input: Story = { render: () => <InputDemo /> };

/** Saved without a score: the empty stars turn red, with the words beside them. */
export const InputInvalid: Story = { render: () => <InputDemo invalid /> };

import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";
import { fn } from "storybook/test";

import { SearchField, type SearchFieldProps } from "./search-field";

/** Shows the applied search, so the debounce, Enter, blur and Escape behaviour is visible. */
function SearchFieldDemo(props: SearchFieldProps): React.JSX.Element {
  const [applied, setApplied] = useState(props.value);

  return (
    <div className="flex w-80 max-w-full flex-col gap-2">
      <SearchField
        {...props}
        className="md:w-full"
        value={applied}
        onSearch={(next) => {
          setApplied(next);
          props.onSearch(next);
        }}
      />
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {applied === "" ? "No search applied" : `Searching for “${applied}”`}
      </p>
    </div>
  );
}

const meta = {
  title: "Patterns/SearchField",
  component: SearchField,
  args: {
    label: "Search leads",
    value: "",
    placeholder: "Name, phone or lead code",
    onSearch: fn(),
    debounceMs: 300,
  },
  render: (args) => <SearchFieldDemo {...args} />,
} satisfies Meta<typeof SearchField>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Searches after a 300ms pause, on Enter or on blur. Escape clears. */
export const Default: Story = {};

export const WithAppliedSearch: Story = {
  args: { value: "Patel" },
};

export const SlowDebounce: Story = {
  args: { debounceMs: 1000 },
};

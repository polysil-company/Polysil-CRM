import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";

import { ToggleGroup, ToggleGroupItem } from "./toggle-group";

function ViewModeToggle(): React.JSX.Element {
  const [value, setValue] = useState<string[]>(["table"]);

  return (
    <div className="flex flex-col items-start gap-3">
      <ToggleGroup
        aria-label="View"
        value={value}
        onValueChange={(next) => {
          const [first] = next;
          // Exclusive choice: pressing the active item again keeps it selected.
          if (typeof first === "string") {
            setValue([first]);
          }
        }}
      >
        <ToggleGroupItem value="table">Table</ToggleGroupItem>
        <ToggleGroupItem value="board">Board</ToggleGroupItem>
        <ToggleGroupItem value="map" disabled>
          Map
        </ToggleGroupItem>
      </ToggleGroup>
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Showing the {value[0] ?? "table"} view
      </p>
    </div>
  );
}

const meta = {
  title: "UI/ToggleGroup",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Small exclusive choices: view mode, density, date presets. */
export const ViewMode: Story = {
  render: () => <ViewModeToggle />,
};

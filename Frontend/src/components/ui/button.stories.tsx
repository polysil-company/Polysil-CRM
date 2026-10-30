import {
  Add01Icon,
  ArrowRight01Icon,
  Call02Icon,
  Settings02Icon,
} from "@hugeicons/core-free-icons";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";

import { useAsyncAction } from "@/hooks/use-async-action";
import { createLogger } from "@/lib/logger";

import { Button } from "./button";
import { Checkbox } from "./checkbox";
import { Icon } from "./icon";

const log = createLogger({ file: "components/ui/button.stories.tsx", dataId: "DS-001" });

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** A real save: loading → success, or loading → error with a shake, then back to idle. */
function AsyncSaveDemo(): React.JSX.Element {
  const [failNext, setFailNext] = useState(false);
  const save = useAsyncAction({
    action: async (): Promise<void> => {
      await wait(900);
      if (failNext) {
        throw new Error("The server rejected the save");
      }
    },
    logger: log,
    fn: "handleSaveDemo",
  });

  return (
    <div className="flex flex-col items-start gap-4">
      <Button
        state={save.state}
        loadingLabel="Saving…"
        successLabel="Saved"
        errorLabel="Couldn't save"
        onClick={() => {
          void save.run();
        }}
      >
        Save lead
      </Button>
      <label className="flex items-center gap-2.5 text-sm text-muted-foreground">
        <Checkbox
          checked={failNext}
          onCheckedChange={(checked) => {
            setFailNext(checked);
          }}
        />
        Make the next save fail
      </label>
    </div>
  );
}

const meta = {
  title: "UI/Button",
  component: Button,
  args: {
    children: "Save lead",
    variant: "primary",
    size: "md",
    disabled: false,
    onClick: fn(),
  },
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "outline", "ghost", "destructive", "link"],
    },
    size: { control: "select", options: ["xs", "sm", "md", "lg"] },
    state: { control: "select", options: ["idle", "loading", "success", "error"] },
    progress: { control: { type: "range", min: 0, max: 100, step: 5 } },
  },
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const Variants: Story = {
  render: (args) => (
    <div className="flex flex-wrap items-center gap-3">
      <Button {...args} variant="primary">
        Save lead
      </Button>
      <Button {...args} variant="secondary">
        Save draft
      </Button>
      <Button {...args} variant="outline">
        Export
      </Button>
      <Button {...args} variant="ghost">
        Cancel
      </Button>
      <Button {...args} variant="destructive">
        Mark as lost
      </Button>
      <Button {...args} variant="link">
        View history
      </Button>
    </div>
  ),
};

export const Sizes: Story = {
  render: (args) => (
    <div className="flex flex-col items-start gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button {...args} size="xs">
          Extra small
        </Button>
        <Button {...args} size="sm">
          Small
        </Button>
        <Button {...args} size="md">
          Medium
        </Button>
        <Button {...args} size="lg">
          Large
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button {...args} variant="outline" size="icon-xs" aria-label="Add lead">
          <Icon icon={Add01Icon} />
        </Button>
        <Button {...args} variant="outline" size="icon-sm" aria-label="Add lead">
          <Icon icon={Add01Icon} />
        </Button>
        <Button {...args} variant="outline" size="icon-md" aria-label="Add lead">
          <Icon icon={Add01Icon} />
        </Button>
        <Button {...args} variant="outline" size="icon-lg" aria-label="Add lead">
          <Icon icon={Add01Icon} />
        </Button>
      </div>
    </div>
  ),
};

export const WithIcons: Story = {
  render: (args) => (
    <div className="flex flex-wrap items-center gap-3">
      <Button {...args}>
        <Icon icon={Add01Icon} />
        New lead
      </Button>
      <Button {...args} variant="outline">
        <Icon icon={Call02Icon} />
        Call customer
      </Button>
      <Button {...args} variant="ghost">
        Continue
        <Icon icon={ArrowRight01Icon} />
      </Button>
      <Button {...args} variant="ghost" size="icon-md" aria-label="Settings">
        <Icon icon={Settings02Icon} />
      </Button>
    </div>
  ),
};

export const Disabled: Story = {
  args: { disabled: true },
};

/** Every async state side by side. Labels share one grid cell, so the width never jumps. */
export const AsyncStates: Story = {
  render: (args) => (
    <div className="flex flex-wrap items-center gap-3">
      <Button {...args} state="idle">
        Save lead
      </Button>
      <Button {...args} state="loading" loadingLabel="Saving…">
        Save lead
      </Button>
      <Button {...args} variant="outline" state="loading" progress={60} loadingLabel="60%">
        Upload photos
      </Button>
      <Button {...args} state="success" successLabel="Saved">
        Save lead
      </Button>
      <Button {...args} state="error" errorLabel="Couldn't save">
        Save lead
      </Button>
    </div>
  ),
};

/** Press it. Tick the box to see the failure path. */
export const AsyncDemo: Story = {
  render: () => <AsyncSaveDemo />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = canvas.getByRole("button", { name: "Save lead" });

    await userEvent.click(button);

    await waitFor(
      async () => {
        await expect(button).toHaveAttribute("data-state", "success");
      },
      { timeout: 3000 },
    );
  },
};

import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type * as React from "react";

import { Field, FieldDescription, FieldError, FieldLabel } from "./field";
import { PasswordInput } from "./password-input";

function PasswordField({
  error,
  disabled = false,
}: {
  error?: string;
  disabled?: boolean;
}): React.JSX.Element {
  return (
    <Field className="w-72">
      <FieldLabel htmlFor="story-password">Password</FieldLabel>
      <PasswordInput
        id="story-password"
        autoComplete="current-password"
        disabled={disabled}
        defaultValue={error ? "wrong-password" : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "story-password-error" : "story-password-help"}
      />
      {error ? null : (
        <FieldDescription id="story-password-help">
          Press a key with Caps Lock on to see the warning.
        </FieldDescription>
      )}
      <FieldError id="story-password-error">{error}</FieldError>
    </Field>
  );
}

const meta = {
  title: "UI/PasswordInput",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <PasswordField />,
};

export const Invalid: Story = {
  render: () => <PasswordField error="Enter your password." />,
};

export const Disabled: Story = {
  render: () => <PasswordField disabled />,
};

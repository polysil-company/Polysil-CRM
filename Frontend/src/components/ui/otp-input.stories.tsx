import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import type * as React from "react";

import { Field, FieldError, FieldLabel } from "./field";
import { OtpInput } from "./otp-input";

function OtpField({
  initialValue = "",
  error,
  disabled = false,
}: {
  initialValue?: string;
  error?: string;
  disabled?: boolean;
}): React.JSX.Element {
  const [code, setCode] = useState(initialValue);
  const [completed, setCompleted] = useState<string | null>(null);

  return (
    <Field className="w-fit">
      <FieldLabel htmlFor="story-code">6-digit code</FieldLabel>
      <OtpInput
        id="story-code"
        value={code}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "story-code-error" : undefined}
        onValueChange={setCode}
        onComplete={setCompleted}
      />
      <FieldError id="story-code-error">{error}</FieldError>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {completed === null ? "Type or paste a code." : `Completed with ${completed}`}
      </p>
    </Field>
  );
}

const meta = {
  title: "UI/OtpInput",
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

/** Focus it and type, or paste "482 913" — non-digits are dropped. */
export const Empty: Story = {
  render: () => <OtpField />,
};

export const PartlyFilled: Story = {
  render: () => <OtpField initialValue="482" />,
};

export const Invalid: Story = {
  render: () => <OtpField initialValue="000000" error="That code didn't work." />,
};

/** An expired code: the field can no longer be used. */
export const Disabled: Story = {
  render: () => <OtpField disabled />,
};

"use client";

import type * as React from "react";

import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

/** CHNL-007, CHNL-008 · The application form's labelled inputs, with "(optional)" and their error. */

export function TextField({
  id,
  label,
  value,
  error,
  optional = false,
  mono = false,
  inputMode,
  type,
  max,
  maxLength,
  placeholder,
  description,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  optional?: boolean;
  mono?: boolean;
  inputMode?: "numeric" | "decimal" | "email" | "tel";
  type?: "date";
  /** For a date: the latest allowed, `YYYY-MM-DD`. */
  max?: string;
  maxLength?: number;
  placeholder?: string | undefined;
  description?: string | undefined;
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy = error !== undefined ? `${id}-error` : description ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <Input
        id={id}
        value={value}
        inputMode={inputMode}
        type={type}
        max={max}
        maxLength={maxLength}
        placeholder={placeholder}
        autoComplete="off"
        className={mono ? "font-mono" : undefined}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {description !== undefined && error === undefined ? (
        <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}

export function TextArea({
  id,
  label,
  value,
  error,
  optional = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  optional?: boolean;
  onChange: (next: string) => void;
}): React.JSX.Element {
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <Textarea
        id={id}
        rows={2}
        maxLength={500}
        value={value}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={error === undefined ? undefined : `${id}-error`}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}

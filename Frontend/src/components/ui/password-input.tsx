"use client";

import { ViewIcon, ViewOffSlashIcon } from "@hugeicons/core-free-icons";
import { useId, useState } from "react";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Icon } from "./icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./input-group";

export interface PasswordInputProps extends Omit<React.ComponentProps<"input">, "type"> {
  className?: string;
}

/**
 * A password field with a show/hide toggle and a Caps Lock warning.
 *
 * The toggle keeps one name ("Show password") and reports its state with
 * aria-pressed, so screen readers hear "Show password, toggle button, pressed".
 * Browsers only expose Caps Lock on a key event, so the warning appears after
 * the first key press in the field.
 */
export function PasswordInput({
  id,
  className,
  disabled,
  onKeyDown,
  onKeyUp,
  onBlur,
  "aria-describedby": describedBy,
  ...props
}: PasswordInputProps): React.JSX.Element {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const capsLockId = `${inputId}-caps-lock`;
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  const readCapsLock = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    setCapsLock(event.getModifierState("CapsLock"));
  };

  return (
    <>
      <InputGroup className={cn("pr-1", disabled && "opacity-50", className)}>
        <InputGroupInput
          id={inputId}
          type={visible ? "text" : "password"}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          disabled={disabled}
          aria-describedby={
            [describedBy, capsLock ? capsLockId : undefined].filter(Boolean).join(" ") || undefined
          }
          onKeyDown={(event) => {
            readCapsLock(event);
            onKeyDown?.(event);
          }}
          onKeyUp={(event) => {
            readCapsLock(event);
            onKeyUp?.(event);
          }}
          onBlur={(event) => {
            setCapsLock(false);
            onBlur?.(event);
          }}
          {...props}
        />
        <InputGroupAddon align="end">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Show password"
            aria-pressed={visible}
            aria-controls={inputId}
            disabled={disabled}
            onClick={() => {
              setVisible((current) => !current);
            }}
          >
            <Icon icon={visible ? ViewOffSlashIcon : ViewIcon} />
          </Button>
        </InputGroupAddon>
      </InputGroup>
      {capsLock ? (
        <p id={capsLockId} className="text-xs/normal text-warning">
          Caps Lock is on
        </p>
      ) : null}
    </>
  );
}

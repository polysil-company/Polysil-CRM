"use client";

import { useEffect, useEffectEvent } from "react";

import { isApplePlatform } from "./use-modifier-key";

export interface KeyboardShortcut {
  /** `KeyboardEvent.key`, compared case-insensitively: "k", "/", "Escape". */
  readonly key: string;
  /** ⌘ on Apple devices, Ctrl elsewhere. */
  readonly mod?: boolean;
  readonly shift?: boolean;
  /** Also fire while typing in an input, textarea or editable element. */
  readonly allowInEditable?: boolean;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

export function matchesShortcut(
  event: KeyboardEvent,
  shortcut: KeyboardShortcut,
  apple: boolean = isApplePlatform(),
): boolean {
  if (event.key.toLowerCase() !== shortcut.key.toLowerCase()) {
    return false;
  }
  const modPressed = apple ? event.metaKey : event.ctrlKey;
  return (
    Boolean(shortcut.mod) === modPressed &&
    Boolean(shortcut.shift) === event.shiftKey &&
    !event.altKey
  );
}

/**
 * Registers a global keyboard shortcut for as long as the component is mounted.
 * Whatever a shortcut opens must not animate — it is used many times a day.
 */
export function useKeyboardShortcut(
  shortcut: KeyboardShortcut,
  onTrigger: (event: KeyboardEvent) => void,
  enabled = true,
): void {
  const handleKeyDown = useEffectEvent((event: KeyboardEvent) => {
    if (event.defaultPrevented || event.isComposing || event.repeat) {
      return;
    }
    if (!matchesShortcut(event, shortcut)) {
      return;
    }
    if (!shortcut.allowInEditable && isEditableTarget(event.target)) {
      return;
    }
    event.preventDefault();
    onTrigger(event);
  });

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const listener = (event: KeyboardEvent): void => {
      handleKeyDown(event);
    };
    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
    };
  }, [enabled]);
}

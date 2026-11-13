import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { isEditableTarget, matchesShortcut, useKeyboardShortcut } from "./use-keyboard-shortcut";

describe("[APP-001] keyboard shortcuts", () => {
  it("maps mod to ⌘ on Apple devices and Ctrl elsewhere", () => {
    const metaK = new KeyboardEvent("keydown", { key: "k", metaKey: true });
    const ctrlK = new KeyboardEvent("keydown", { key: "K", ctrlKey: true });

    expect(matchesShortcut(metaK, { key: "k", mod: true }, true)).toBe(true);
    expect(matchesShortcut(metaK, { key: "k", mod: true }, false)).toBe(false);
    expect(matchesShortcut(ctrlK, { key: "k", mod: true }, false)).toBe(true);
  });

  it("requires the exact modifiers", () => {
    const shiftK = new KeyboardEvent("keydown", { key: "k", ctrlKey: true, shiftKey: true });
    const altSlash = new KeyboardEvent("keydown", { key: "/", altKey: true });

    expect(matchesShortcut(shiftK, { key: "k", mod: true }, false)).toBe(false);
    expect(matchesShortcut(shiftK, { key: "k", mod: true, shift: true }, false)).toBe(true);
    expect(matchesShortcut(altSlash, { key: "/" }, false)).toBe(false);
  });

  it("knows which targets are editable", () => {
    expect(isEditableTarget(document.createElement("input"))).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("button"))).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });

  it("fires for a matching key and ignores the same key typed into an input", () => {
    const onTrigger = vi.fn();
    renderHook(() => {
      useKeyboardShortcut({ key: "/" }, onTrigger);
    });

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);

    const input = document.createElement("input");
    document.body.append(input);
    act(() => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true }));
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);
    input.remove();
  });

  it("stops listening when disabled", () => {
    const onTrigger = vi.fn();
    renderHook(() => {
      useKeyboardShortcut({ key: "/" }, onTrigger, false);
    });

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "/" }));
    });
    expect(onTrigger).not.toHaveBeenCalled();
  });
});

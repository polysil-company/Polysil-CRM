import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useShiftWheelScroll } from "./use-shift-wheel-scroll";

function ScrollBox(): React.JSX.Element {
  const ref = useShiftWheelScroll<HTMLDivElement>();
  return <div ref={ref} data-testid="box" />;
}

/** jsdom does no layout, so the scroll sizes are declared by hand. */
function mountScrollBox({
  scrollWidth = 600,
  clientWidth = 300,
  scrollLeft = 0,
}: { scrollWidth?: number; clientWidth?: number; scrollLeft?: number } = {}): HTMLElement {
  render(<ScrollBox />);
  const box = screen.getByTestId("box");
  Object.defineProperty(box, "scrollWidth", { value: scrollWidth, configurable: true });
  Object.defineProperty(box, "clientWidth", { value: clientWidth, configurable: true });
  Object.defineProperty(box, "scrollLeft", { value: scrollLeft, writable: true });
  return box;
}

function wheel(box: HTMLElement, options: { deltaY: number; shiftKey?: boolean }): WheelEvent {
  const event = new WheelEvent("wheel", {
    deltaY: options.deltaY,
    shiftKey: options.shiftKey ?? true,
    bubbles: true,
    cancelable: true,
  });
  box.dispatchEvent(event);
  return event;
}

describe("[DS-001] useShiftWheelScroll", () => {
  it("scrolls sideways by the wheel's distance while Shift is held", () => {
    const box = mountScrollBox();

    const event = wheel(box, { deltaY: 120 });

    expect(box.scrollLeft).toBe(120);
    expect(event.defaultPrevented).toBe(true);
  });

  it("leaves a plain wheel to the page", () => {
    const box = mountScrollBox();

    const event = wheel(box, { deltaY: 120, shiftKey: false });

    expect(box.scrollLeft).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });

  it("lets the page scroll on once the table reaches its edge", () => {
    const box = mountScrollBox({ scrollLeft: 300 });

    const atEnd = wheel(box, { deltaY: 120 });
    expect(box.scrollLeft).toBe(300);
    expect(atEnd.defaultPrevented).toBe(false);

    const backwards = wheel(box, { deltaY: -120 });
    expect(box.scrollLeft).toBe(180);
    expect(backwards.defaultPrevented).toBe(true);
  });

  it("does nothing when everything already fits", () => {
    const box = mountScrollBox({ scrollWidth: 300 });

    const event = wheel(box, { deltaY: 120 });

    expect(box.scrollLeft).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });
});

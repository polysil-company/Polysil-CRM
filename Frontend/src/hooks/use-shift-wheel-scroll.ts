"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * Shift + mouse wheel scrolls a container sideways — for wide tables, where the columns
 * run past the edge but the wheel only moves the page.
 *
 * Put the returned ref on the element that scrolls. A wheel that arrives already
 * horizontal (some browsers and every trackpad swipe) is left alone, and at either edge
 * the wheel falls through so the page keeps scrolling.
 */
export function useShiftWheelScroll<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T>(null);

  useEffect(() => {
    const element = ref.current;
    if (element === null) {
      return undefined;
    }

    const handleWheel = (event: WheelEvent): void => {
      if (!event.shiftKey || event.deltaY === 0) {
        return;
      }
      const maxScrollLeft = element.scrollWidth - element.clientWidth;
      if (maxScrollLeft <= 0) {
        return;
      }
      const atStart = element.scrollLeft <= 0;
      const atEnd = element.scrollLeft >= maxScrollLeft;
      if ((event.deltaY < 0 && atStart) || (event.deltaY > 0 && atEnd)) {
        return;
      }
      // The listener is non-passive so this can replace the page's vertical scroll.
      event.preventDefault();
      element.scrollLeft = Math.min(maxScrollLeft, Math.max(0, element.scrollLeft + event.deltaY));
    };

    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      element.removeEventListener("wheel", handleWheel);
    };
  }, []);

  return ref;
}

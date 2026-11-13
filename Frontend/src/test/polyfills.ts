/**
 * Browser APIs that jsdom does not implement but Base UI, cmdk and our theme
 * store rely on. Imported once from vitest.setup.ts.
 */

class StaticMediaQueryList extends EventTarget implements MediaQueryList {
  readonly matches = false;
  readonly media: string;
  onchange: ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | null = null;

  constructor(media: string) {
    super();
    this.media = media;
  }

  addListener(): void {
    // Deprecated API — intentionally a no-op in tests.
  }

  removeListener(): void {
    // Deprecated API — intentionally a no-op in tests.
  }
}

if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList => new StaticMediaQueryList(query);
}

class NoopResizeObserver implements ResizeObserver {
  observe(): void {
    // Layout is not computed in jsdom.
  }

  unobserve(): void {
    // Layout is not computed in jsdom.
  }

  disconnect(): void {
    // Layout is not computed in jsdom.
  }
}

if (typeof globalThis.ResizeObserver !== "function") {
  globalThis.ResizeObserver = NoopResizeObserver;
}

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = function scrollIntoView(): void {
    // Scrolling is not simulated in jsdom.
  };
}

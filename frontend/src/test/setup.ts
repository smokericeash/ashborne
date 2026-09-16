import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

class TestResizeObserver implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => vi.stubGlobal("ResizeObserver", TestResizeObserver));

Object.defineProperties(HTMLElement.prototype, {
  offsetWidth: { configurable: true, get: () => 800 },
  offsetHeight: { configurable: true, get: () => 300 },
});

HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
  x: 0,
  y: 0,
  width: 800,
  height: 300,
  top: 0,
  right: 800,
  bottom: 300,
  left: 0,
  toJSON: () => ({}),
}));

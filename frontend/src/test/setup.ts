import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Make @testing-library/dom's waitFor work with vitest fake timers.
// The library checks `typeof jest !== 'undefined'` to decide whether fake
// timers are active and uses `jest.advanceTimersByTime` to drive retries.
// We expose a minimal `jest` shim so the detection works and the timer
// advancement calls vitest's own implementation.
// See: https://github.com/testing-library/dom-testing-library/issues/987
// eslint-disable-next-line @typescript-eslint/no-explicit-any
if (typeof (globalThis as any).jest === "undefined") {
    Object.defineProperty(globalThis, "jest", {
        configurable: true,
        writable: true,
        value: {
            advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms),
        },
    });

    // Patch setTimeout to expose the clock detection flag that
    // jestFakeTimersAreEnabled() looks for when fake timers are in use.
    const originalUseFakeTimers = vi.useFakeTimers.bind(vi);
    const originalUseRealTimers = vi.useRealTimers.bind(vi);

    vi.useFakeTimers = (...args: Parameters<typeof vi.useFakeTimers>) => {
        const result = originalUseFakeTimers(...args);
        // Mark setTimeout so jestFakeTimersAreEnabled returns true
        (setTimeout as unknown as Record<string, unknown>)["_isMockFunction"] = true;
        return result;
    };

    vi.useRealTimers = () => {
        const result = originalUseRealTimers();
        delete (setTimeout as unknown as Record<string, unknown>)["_isMockFunction"];
        return result;
    };
}

afterEach(() => {
    cleanup();
});

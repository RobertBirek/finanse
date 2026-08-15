import { afterEach, describe, expect, it, vi } from "vitest";
import { localTodayIso } from "./date";

describe("localTodayIso", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("zwraca lokalną datę kalendarzową, a nie UTC, tuż po północy", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-15T22:30:00.000Z"));
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(-120);

    expect(new Date().toISOString().slice(0, 10)).toBe("2026-08-15");
    expect(localTodayIso()).toBe("2026-08-16");
  });
});

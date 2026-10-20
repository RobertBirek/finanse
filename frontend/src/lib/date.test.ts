import { afterEach, describe, expect, it, vi } from "vitest";
import {
  formatCalendarDate,
  formatLocalTime,
  localDateIso,
  localDayRange,
  localTodayIso,
} from "./date";

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

describe("local date boundaries", () => {
  it("formats a time in the user's timezone instead of slicing UTC", () => {
    const iso = "2026-10-20T07:00:00Z";
    expect(formatLocalTime(iso)).toBe(
      new Intl.DateTimeFormat("pl-PL", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(iso)),
    );
    expect(formatLocalTime("invalid")).toBe("—");
  });
  it("preserves date-only values without UTC shifts", () => {
    expect(formatCalendarDate("2026-10-20")).toBe("20.10.2026");
    expect(localDateIso(new Date(2026, 9, 20, 0, 30))).toBe("2026-10-20");
  });
  it("ends each range at the last millisecond of the local calendar day", () => {
    for (const date of [new Date(2026, 2, 29), new Date(2026, 9, 25)]) {
      const range = localDayRange(date);
      expect(new Date(range.start_time).getHours()).toBe(0);
      const end = new Date(range.end_time);
      expect(end.getHours()).toBe(23);
      expect(end.getMilliseconds()).toBe(999);
      expect(localDateIso(end)).toBe(localDateIso(date));
      const expectedNext = new Date(
        date.getFullYear(),
        date.getMonth(),
        date.getDate() + 1,
      );
      expect(new Date(range.end_time).getTime() + 1).toBe(
        expectedNext.getTime(),
      );
    }
  });
});

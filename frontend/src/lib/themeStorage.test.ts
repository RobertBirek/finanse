import { afterEach, describe, expect, it, vi } from "vitest";
import { readThemePreference, writeThemePreference } from "./theme";

afterEach(() => vi.restoreAllMocks());
describe("theme storage resilience", () => {
  it("defaults to light when browser storage is denied", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Denied", "SecurityError");
    });
    expect(readThemePreference()).toBe("light");
  });
  it("does not break navigation when the preference cannot be persisted", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Denied", "SecurityError");
    });
    expect(() => writeThemePreference("dark")).not.toThrow();
  });
});

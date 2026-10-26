import { describe, expect, it } from "vitest";
import { readTheme } from "./theme";

describe("readTheme", () => {
  it("uses only the persisted light or dark preference", () => {
    expect(readTheme("dark")).toBe("dark");
    expect(readTheme("light")).toBe("light");
    expect(readTheme("anything else")).toBe("light");
  });
});

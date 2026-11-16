import { describe, expect, it } from "vitest";
import {
  openingBalancePayload,
  parseSignedMinor,
  openingBalanceDraft,
} from "./openingBalances";

describe("signed BO money is parsed without rounding", () => {
  it.each([
    ["123,45", 12345],
    ["-123,45", -12345],
    ["+123.45", 12345],
    ["0", 0],
    ["", 0],
    ["-0", 0],
    [" 1 234,56 ", 123456],
    ["90071992547409,91", 9007199254740991],
    ["-90071992547409,91", -9007199254740991],
  ])("parses %s exactly", (raw, amount) => {
    expect(parseSignedMinor(raw)).toBe(amount);
  });
  it.each([
    "1,234",
    "--1",
    "1e3",
    "NaN",
    "-",
    "90071992547409,92",
    "-90071992547409,92",
  ])("rejects lossy or malformed %s", (raw) =>
    expect(parseSignedMinor(raw)).toBeNull(),
  );
  it("requires a date and an explicit foreign quote only for nonzero BO", () => {
    expect(
      openingBalancePayload(
        { amount: "1", date: "2026-11-16", fxRate: "" },
        "EUR",
      ),
    ).toBeNull();
    expect(
      openingBalancePayload(
        { amount: "-1", date: "2026-11-16", fxRate: "4,123456" },
        "EUR",
      ),
    ).toEqual({ amount_minor: -100, date: "2026-11-16", fx_rate: "4.123456" });
    expect(
      openingBalancePayload(
        { amount: "", date: "2026-11-16", fxRate: "" },
        "USD",
      ),
    ).toEqual({ amount_minor: 0, date: "2026-11-16" });
    expect(
      openingBalancePayload({ amount: "1", date: "", fxRate: "" }, "PLN"),
    ).toBeNull();
    expect(
      openingBalancePayload(
        { amount: "1", date: "2026-02-30", fxRate: "" },
        "PLN",
      ),
    ).toBeNull();
    expect(
      openingBalancePayload(
        { amount: "1", date: "2026-11-16", fxRate: "4.1234567" },
        "EUR",
      ),
    ).toBeNull();
  });
  it("keeps the last cent when building an editor draft at the API boundary", () => {
    expect(
      openingBalanceDraft({
        amount_minor: -9007199254740991,
        date: "2026-11-16",
        fx_rate: null,
        version: 1,
        can_edit: true,
        blocked_reason: null,
      }).amount,
    ).toBe("-90071992547409,91");
  });
});

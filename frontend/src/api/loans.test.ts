import { describe, expect, it } from "vitest";
import { loanAmountToGrosze, loanApiErrorMessage } from "./loans";

describe("loanAmountToGrosze", () => {
  it("allows zero components but keeps amounts exact and safe", () => {
    expect(loanAmountToGrosze("0")).toBe(0);
    expect(loanAmountToGrosze("900,00")).toBe(90000);
    expect(loanAmountToGrosze("90071992547409,92")).toBeNull();
  });
});

describe("loanApiErrorMessage", () => {
  it("turns FastAPI validation arrays into a safe message", () => {
    expect(
      loanApiErrorMessage({
        response: { data: { detail: [{ msg: "Field required" }] } },
      }),
    ).toBe(
      "Nie udało się zapisać danych. Sprawdź formularz i spróbuj ponownie.",
    );
  });
});

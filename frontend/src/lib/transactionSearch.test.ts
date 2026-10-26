import { describe, expect, it } from "vitest";
import { transactionSearchParams } from "./transactionSearch";

describe("transactionSearchParams descendant filter", () => {
  it("preserves report budget-account scope in the API request", () => {
    expect(
      transactionSearchParams(new URLSearchParams("budget_accounts_only=true")),
    ).toHaveProperty("budget_accounts_only", true);
  });
  it("includes an explicit descendant category filter", () => {
    expect(
      transactionSearchParams(
        new URLSearchParams("category_id=home&include_descendants=true"),
      ),
    ).toMatchObject({ category_id: "home", include_descendants: true });
  });

  it("keeps the backend exact-match default when the option is absent", () => {
    expect(
      transactionSearchParams(new URLSearchParams("category_id=home")),
    ).not.toHaveProperty("include_descendants");
  });

  it("rejects malformed descendant filter values", () => {
    expect(() =>
      transactionSearchParams(new URLSearchParams("include_descendants=yes")),
    ).toThrow("Filtr podkategorii musi mieć wartość tak lub nie.");
  });
});

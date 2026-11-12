import { describe, expect, it } from "vitest";
import { billPaymentPresentation } from "./billPaymentPresentation";

describe("declaration is not ledger reconciliation", () => {
  it("removes the payable amount without hiding the unlinked amount", () => {
    expect(
      billPaymentPresentation({
        declaration: "declared_paid",
        remaining_minor: 10000,
        reconciliation: "none",
      }),
    ).toEqual({
      payableMinor: 0,
      unlinkedMinor: 10000,
      declared: true,
      statusLabel: "Opłacona deklaracyjnie — bez powiązania z księgą",
    });
  });
  it("covers the whole remainder after a partial real allocation", () => {
    expect(
      billPaymentPresentation({
        declaration: "declared_paid",
        remaining_minor: 6000,
        reconciliation: "partial",
      }),
    ).toEqual({
      payableMinor: 0,
      unlinkedMinor: 6000,
      declared: true,
      statusLabel: "Opłacona deklaracyjnie — częściowo powiązana z księgą",
    });
  });
  it("prioritizes full real reconciliation over the earlier declaration", () => {
    expect(
      billPaymentPresentation({
        declaration: "declared_paid",
        remaining_minor: 0,
        reconciliation: "full",
      }).statusLabel,
    ).toBe("Rozliczona z księgą");
  });
  it("restores only the real unlinked remainder on undo", () => {
    expect(
      billPaymentPresentation({
        declaration: "payable",
        remaining_minor: 6000,
        reconciliation: "partial",
      }).payableMinor,
    ).toBe(6000);
  });
});

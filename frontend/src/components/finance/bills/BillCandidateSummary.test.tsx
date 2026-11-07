import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BillCandidate } from "../../../api/bills";
import { BillCandidateSummary } from "./BillCandidateSummary";

const candidate: BillCandidate = {
  transaction_id: "t1",
  posting_id: "p1",
  date: "2026-11-02",
  account: "Karta",
  amount_minor: 10000,
  unallocated_minor: 6000,
  reasons: ["amount_exact", "date_within_window"],
  legacy_inbox_reference: null,
  recurring_conflicts: [],
  recurring_forecast_before_pln: null,
  recurring_forecast_after_pln: null,
};
const evidence = {
  description: "Zakup u dostawcy",
  currency: "PLN" as const,
  purchase_date: "2026-10-30",
  purchase_date_source: "manual" as const,
  booking_date: "2026-11-02",
  booking_date_source: "bank" as const,
  date_comparison: {
    transaction_basis: "purchase" as const,
    transaction_date: "2026-10-30",
    document_basis: "sale" as const,
    document_date: "2026-10-30",
    delta_days: 0,
    within_window: true,
  },
  supplier_name_in_description: true,
  planned_account_matches: false,
  legacy_date_before_window: false,
  purchase_within_window: true,
};

describe("BillCandidateSummary", () => {
  it("shows dates, provenance, original amount, capacity and controlled reasons", () => {
    render(<BillCandidateSummary candidate={{ ...candidate, evidence }} />);
    expect(screen.getByText(/Kwota płatności: 100.00 PLN/)).toBeInTheDocument();
    expect(screen.getByText(/Nieprzydzielone: 60.00 PLN/)).toBeInTheDocument();
    expect(screen.getByText(/Zakup: 2026-10-30.*ręcznie/)).toBeInTheDocument();
    expect(
      screen.getByText(/Księgowanie: 2026-11-02.*bank/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Porównanie: zakup 2026-10-30.*sprzedaż 2026-10-30.*0 dni/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Nazwa sprzedawcy z dokumentu występuje w opisie płatności",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Inne konto niż zaplanowane/)).toBeInTheDocument();
    expect(
      screen.getByText(/Kwota płatności równa sumie dokumentu/),
    ).toBeInTheDocument();
  });

  it("does not invent purchase or booking semantics for an older API response", () => {
    render(<BillCandidateSummary candidate={candidate} />);
    expect(
      screen.getByText(/Data zapisu — znaczenie nieustalone: 2026-11-02/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Zakup:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Księgowanie:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Porównanie:/)).not.toBeInTheDocument();
  });

  it("escapes text, ignores unknown reasons, and does not call missing name evidence a mismatch", () => {
    const html = "<img src=x onerror=alert(1)>";
    const { container } = render(
      <BillCandidateSummary
        candidate={{
          ...candidate,
          reasons: ["date_older_than_window", "<script>bad</script>"],
          evidence: {
            ...evidence,
            description: html,
            supplier_name_in_description: false,
          },
        }}
      />,
    );
    expect(screen.getByText(html)).toBeInTheDocument();
    expect(container.querySelector("img,script")).toBeNull();
    expect(screen.queryByText("<script>bad</script>")).not.toBeInTheDocument();
    expect(screen.queryByText(/niezgodny kontrahent/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Data zapisu poza domyślnym oknem/),
    ).toBeInTheDocument();
  });

  it.each(["manual", "bank", "document", "import"] as const)(
    "labels the %s source without claiming verified identity",
    (source) => {
      const names = {
        manual: "ręcznie",
        bank: "bank",
        document: "dokument",
        import: "import",
      };
      render(
        <BillCandidateSummary
          candidate={{
            ...candidate,
            evidence: { ...evidence, purchase_date_source: source },
          }}
        />,
      );
      expect(
        screen.getByText(new RegExp(`Zakup: 2026-10-30.*${names[source]}`)),
      ).toBeInTheDocument();
    },
  );
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BillCoverageDialog } from "./BillCoverageDialog";

const unlink = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: [], isLoading: false }),
}));
vi.mock("../../../api/bills", () => ({
  stableKey: () => "stable-key",
  useBillCoverage: () => ({
    decide: { mutate: vi.fn(), isPending: false, error: null },
    unlink: { mutate: unlink, isPending: false, error: null },
  }),
}));

const bill = {
  id: "bill-1",
  version: 7,
  coverage: {
    scheduled_item_id: "scheduled-1",
    occurrence_date: "2026-10-15",
    choice: "replace" as const,
    source_lifecycle: "active" as const,
  },
};

describe("BillCoverageDialog", () => {
  it("requires an explicit confirmation before unlinking coverage that restores the estimate", () => {
    render(<BillCoverageDialog bill={bill as never} onClose={vi.fn()} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Odłącz i przywróć estymatę" }),
    );
    expect(unlink).not.toHaveBeenCalled();
    expect(screen.getByText(/potwierdź.*przywrócona/i)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź odłączenie" }),
    );
    expect(unlink).toHaveBeenCalledWith(
      expect.objectContaining({
        billId: "bill-1",
        expected_version: 7,
        idempotencyKey: "stable-key",
      }),
      expect.anything(),
    );
  });
});

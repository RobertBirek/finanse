import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { BillCoverageDialog } from "./BillCoverageDialog";

const activeBill = {
  id: "bill-1",
  version: 4,
  total_minor: 10000,
  remaining_minor: 10000,
  coverage: null,
  currency: "PLN",
};
const coveredBill = {
  ...activeBill,
  coverage: {
    scheduled_item_id: "scheduled-1",
    occurrence_date: "2026-10-15",
    choice: "replace" as const,
    source_lifecycle: "active" as const,
  },
};

afterEach(() => vi.restoreAllMocks());
function renderDialog(
  bill: typeof activeBill | typeof coveredBill = activeBill,
) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <BillCoverageDialog bill={bill as never} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}
function arrangeConflict() {
  vi.spyOn(api, "get").mockImplementation((url) => {
    if (String(url).includes("coverage-candidates"))
      return Promise.resolve({
        data: [
          {
            scheduled_item_id: "scheduled-1",
            occurrence_date: "2026-10-15",
            name: "Czynsz",
            estimate_amount_pln: 7000,
          },
        ],
      } as never);
    return Promise.resolve({
      data: { ...activeBill, version: 5, remaining_minor: 6000 },
    } as never);
  });
}
describe("BillCoverageDialog conflicts", () => {
  it("blocks a coverage decision after 409 until it refetches and acknowledges a new version", async () => {
    arrangeConflict();
    const post = vi
      .spyOn(api, "post")
      .mockRejectedValue({ response: { status: 409 } });
    renderDialog();
    fireEvent.click(await screen.findByLabelText(/Czynsz/));
    fireEvent.click(screen.getByRole("button", { name: "Zastąp estymatę" }));
    await screen.findByRole("alert");
    expect(
      screen.getByRole("button", { name: "Zastąp estymatę" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Zastąp estymatę" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toMatchObject({ version: 5 });
  });

  it("blocks coverage unlink after 409 until it refetches and acknowledges a new version", async () => {
    arrangeConflict();
    const remove = vi
      .spyOn(api, "delete")
      .mockRejectedValue({ response: { status: 409 } });
    renderDialog(coveredBill);
    await screen.findByText(/wystąpienie 2026-10-15/i);
    fireEvent.click(
      screen.getByRole("button", { name: "Odłącz i przywróć estymatę" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź odłączenie" }),
    );
    await screen.findByRole("alert");
    expect(
      screen.getByRole("button", { name: "Potwierdź odłączenie" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź odłączenie" }),
    );
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    expect(
      (remove.mock.calls[1][1] as { params: unknown }).params,
    ).toMatchObject({ expected_version: 5 });
  });
});

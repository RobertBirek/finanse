import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { BillPaymentDialog } from "./BillPaymentDialog";

const bill = {
  id: "bill-1",
  supplier_name: "Dostawca",
  description: "Usługa",
  payment_account_id: null,
  category_id: null,
  remaining_minor: 6000,
  version: 4,
};

afterEach(() => vi.restoreAllMocks());
function renderDialog() {
  vi.spyOn(api, "get").mockImplementation((url) => {
    if (String(url).includes("candidates"))
      return Promise.resolve({
        data: {
          items: [
            {
              transaction_id: "t1",
              posting_id: "p1",
              date: "2026-10-01",
              account: "Karta",
              amount_minor: 6000,
              unallocated_minor: 6000,
              reasons: [],
              legacy_inbox_reference: null,
              recurring_conflicts: ["schedule"],
              recurring_forecast_before_pln: 10000,
              recurring_forecast_after_pln: 0,
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        },
      } as never);
    return Promise.resolve({ data: [] } as never);
  });
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
      <BillPaymentDialog bill={bill as never} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("BillPaymentDialog", () => {
  it("shows existing candidates, requires forecast acknowledgement, and says linking does not send a transfer", async () => {
    renderDialog();
    expect(
      await screen.findByText(/Powiązanie nie zleca przelewu/),
    ).toBeInTheDocument();
    const candidate = await screen.findByText(/Karta.*2026-10-01/);
    fireEvent.click(candidate.closest("label")!);
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Rozumiem wpływ/));
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeEnabled();
  });

  it("sends the recurring-conflict acknowledgement with the selected existing payment", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue({ data: bill } as never);
    renderDialog();
    const candidate = await screen.findByText(/Karta.*2026-10-01/);
    fireEvent.click(candidate.closest("label")!);
    fireEvent.click(screen.getByLabelText(/Rozumiem wpływ/));
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0]).toEqual([
      "/finance/bills/bill-1/allocations",
      expect.objectContaining({
        version: 4,
        posting_id: "p1",
        amount_minor: 6000,
        confirm_recurring_conflict: true,
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": expect.any(String),
        }),
      }),
    ]);
  });

  it("preserves entered fields after 409, refetches the current bill, and requires a new decision", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { detail: "version_conflict" } },
    });
    renderDialog();
    const candidate = await screen.findByText(/Karta.*2026-10-01/);
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "12.34" },
    });
    fireEvent.click(candidate.closest("label")!);
    fireEvent.click(screen.getByLabelText(/Rozumiem wpływ/));
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Kwota (PLN)")).toHaveValue("12.34");
    expect(screen.getByText(/Odśwież dokument i porównaj/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    ).toBeInTheDocument();
    const firstKey = (
      post.mock.calls[0][2] as { headers: { "Idempotency-Key": string } }
    ).headers["Idempotency-Key"];
    vi.spyOn(api, "get").mockResolvedValue({
      data: { ...bill, version: 5, paid_minor: 4000, remaining_minor: 6000 },
    } as never);
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(
      (post.mock.calls[1][2] as { headers: { "Idempotency-Key": string } })
        .headers["Idempotency-Key"],
    ).not.toBe(firstKey);
    expect(post.mock.calls[1][1]).toMatchObject({
      posting_id: "p1",
      amount_minor: 1234,
      version: 5,
    });
  });

  it("uses a fresh idempotency key after the user changes a failed allocation decision", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValue({
      response: { status: 409, data: { detail: "version_conflict" } },
    });
    renderDialog();
    const candidate = await screen.findByText(/Karta.*2026-10-01/);
    fireEvent.click(candidate.closest("label")!);
    fireEvent.click(screen.getByLabelText(/Rozumiem wpływ/));
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await screen.findByRole("alert");
    const firstKey = (
      post.mock.calls[0][2] as { headers: { "Idempotency-Key": string } }
    ).headers["Idempotency-Key"];

    vi.spyOn(api, "get").mockResolvedValue({
      data: { ...bill, version: 5 },
    } as never);
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "59.99" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));

    expect(
      (post.mock.calls[1][2] as { headers: { "Idempotency-Key": string } })
        .headers["Idempotency-Key"],
    ).not.toBe(firstKey);
    expect(post.mock.calls[1][1]).toMatchObject({
      amount_minor: 5999,
      version: 5,
    });
  });

  it("records a separate PLN expense only after showing candidates and invalidates ledger views", async () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (String(url).includes("candidates"))
        return Promise.resolve({
          data: { items: [], total: 0, limit: 20, offset: 0 },
        } as never);
      if (url === "/finance/accounts")
        return Promise.resolve({
          data: [
            {
              id: "cash-1",
              name: "Portfel",
              type: "cash",
              currency: "PLN",
              is_active: true,
            },
          ],
        } as never);
      return Promise.resolve({
        data: [
          {
            id: "category-1",
            name: "Usługi",
            type: "expense",
            is_active: true,
          },
        ],
      } as never);
    });
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue({ data: bill } as never);
    render(
      <QueryClientProvider client={client}>
        <BillPaymentDialog bill={bill as never} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText(/Powiązanie nie zleca przelewu/),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Zarejestruj płatność" }),
    );
    await screen.findByRole("option", { name: /Portfel \(gotówka\)/ });
    fireEvent.change(screen.getByLabelText("Aktywne konto"), {
      target: { value: "cash-1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "category-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Zarejestruj wydatek" }),
    );

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0]).toEqual([
      "/finance/bills/bill-1/payments",
      expect.objectContaining({
        version: 4,
        account_id: "cash-1",
        category_id: "category-1",
        amount_minor: 6000,
        confirm_new_payment: true,
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": expect.any(String),
        }),
      }),
    ]);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["finance", "transactions"],
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["finance", "budget"],
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["finance", "cashflow"],
    });
  });
});

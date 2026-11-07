import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { BillPaymentDialog } from "./BillPaymentDialog";

afterEach(() => vi.restoreAllMocks());
const bill = {
  id: "bill-match",
  supplier_name: "Dostawca",
  description: "Usługa",
  payment_account_id: null,
  category_id: null,
  total_minor: 10000,
  currency: "PLN",
  remaining_minor: 6000,
  version: 4,
  sale_date: "2026-10-30",
  issue_date: "2026-10-30",
  due_date: "2026-11-07",
};
const row = {
  transaction_id: "t1",
  posting_id: "p1",
  date: "2026-11-02",
  account: "Karta",
  amount_minor: 10000,
  unallocated_minor: 6000,
  reasons: [],
  legacy_inbox_reference: null,
  recurring_conflicts: ["recurring"],
  recurring_forecast_before_pln: 10000,
  recurring_forecast_after_pln: 0,
};
const page = { items: [row], total: 40, limit: 20, offset: 0 };
const queryKey = ["finance", "bills", bill.id, "candidates"];
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function setup(
  fetchPage: () => Promise<unknown> = async () => ({ data: page }),
) {
  const get = vi.spyOn(api, "get").mockImplementation((url) => {
    if (String(url).includes("candidates")) return fetchPage() as never;
    if (url === `/finance/bills/${bill.id}`)
      return Promise.resolve({ data: bill }) as never;
    return Promise.resolve({ data: [] }) as never;
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <BillPaymentDialog bill={bill as never} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
  return { client, get, ...view };
}
async function choose() {
  fireEvent.click(await screen.findByRole("radio"));
  fireEvent.click(screen.getByLabelText(/Rozumiem wpływ/));
  expect(screen.getByRole("button", { name: "Powiąż płatność" })).toBeEnabled();
}

describe("payment candidate decision freshness", () => {
  it("distinguishes loading, failure, retry and empty without creating an expense", async () => {
    const pending = deferred<unknown>();
    let response = () => pending.promise;
    const post = vi.spyOn(api, "post");
    const { client } = setup(() => response());
    expect(screen.getByRole("status")).toHaveTextContent(/Pobieranie/);
    await act(async () =>
      pending.resolve(Promise.reject(new Error("offline"))),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Nie udało się pobrać płatności/,
    );
    response = async () => ({ data: { ...page, items: [], total: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));
    expect(
      await screen.findByText("Brak płatności w wybranych filtrach."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
    client.clear();
  });

  it.each([
    ["document_inactive", /Dokument nie jest aktywny/],
    ["document_unapproved", /Zatwierdź dokument/],
    ["currency_unsupported", /Rozliczanie obsługuje tylko PLN/],
    ["document_reconciled", /Dokument jest już rozliczony/],
  ] as const)(
    "separates unavailable %s from empty filters",
    async (reason, message) => {
      setup(async () => ({
        data: { ...page, items: [], total: 0, unavailable_reason: reason },
      }));
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(
        screen.queryByText("Brak płatności w wybranych filtrach."),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Powiąż płatność" }),
      ).toBeDisabled();
    },
  );

  it.each(["text", "from", "to", "older", "next"])(
    "clears radio and acknowledgement on %s change",
    async (control) => {
      setup();
      await choose();
      if (control === "text")
        fireEvent.change(
          screen.getByLabelText("Szukaj istniejącej płatności"),
          { target: { value: "Supplier" } },
        );
      if (control === "from")
        fireEvent.change(screen.getByLabelText("Data od"), {
          target: { value: "2026-10-01" },
        });
      if (control === "to")
        fireEvent.change(screen.getByLabelText("Data do"), {
          target: { value: "2026-12-01" },
        });
      if (control === "older")
        fireEvent.click(screen.getByLabelText("Uwzględnij starsze"));
      if (control === "next")
        fireEvent.click(screen.getByRole("button", { name: "Następne" }));
      await waitFor(() => expect(screen.getByRole("radio")).not.toBeChecked());
      expect(screen.queryByLabelText(/Rozumiem wpływ/)).not.toBeInTheDocument();
      expect(screen.getByLabelText("Kwota (PLN)")).toHaveValue("60.00");
      expect(
        screen.getByRole("button", { name: "Powiąż płatność" }),
      ).toBeDisabled();
    },
  );

  it("invalidates even identical data on refetch and rejects clicks while the result is pending", async () => {
    let pending: ReturnType<typeof deferred<unknown>> | null = null;
    const post = vi.spyOn(api, "post");
    const { client } = setup(() =>
      pending ? pending.promise : Promise.resolve({ data: page }),
    );
    await choose();
    pending = deferred();
    let refreshed!: Promise<void>;
    act(() => {
      refreshed = client.refetchQueries({ queryKey });
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/Pobieranie/);
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    expect(post).not.toHaveBeenCalled();
    await act(async () => {
      pending!.resolve({ data: page });
      await refreshed;
    });
    expect(await screen.findByRole("radio")).not.toBeChecked();
    expect(screen.queryByLabelText(/Rozumiem wpływ/)).not.toBeInTheDocument();
  });

  it("does not revive an old decision when an obsolete filter response arrives late", async () => {
    const old = deferred<unknown>();
    let calls = 0;
    setup(() =>
      ++calls === 2 ? old.promise : Promise.resolve({ data: page }),
    );
    await choose();
    const input = screen.getByLabelText("Szukaj istniejącej płatności");
    fireEvent.change(input, { target: { value: "old" } });
    fireEvent.change(input, { target: { value: "new" } });
    expect(await screen.findByRole("radio")).not.toBeChecked();
    await act(async () => old.resolve({ data: page }));
    expect(screen.getByRole("radio")).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeDisabled();
  });

  it("checks the live cache in the handler before React renders a changed response", async () => {
    const post = vi.spyOn(api, "post");
    const { client } = setup();
    await choose();
    const button = screen.getByRole("button", { name: "Powiąż płatność" });
    act(() => {
      client.setQueriesData(
        { queryKey },
        {
          ...page,
          items: [],
          total: 0,
          unavailable_reason: "document_reconciled",
        },
      );
      fireEvent.click(button);
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("blocks reversed date bounds and nonpositive amounts without a POST", async () => {
    const post = vi.spyOn(api, "post");
    setup();
    await choose();
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "0" },
    });
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Data od"), {
      target: { value: "2026-11-03" },
    });
    fireEvent.change(screen.getByLabelText("Data do"), {
      target: { value: "2026-11-01" },
    });
    expect(
      await screen.findByText(/Data od nie może być późniejsza/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    expect(post).not.toHaveBeenCalled();
  });

  it("retries an uncertain result with the same receipt key, including after reselection", async () => {
    const post = vi.spyOn(api, "post").mockRejectedValue(new Error("timeout"));
    const { client } = setup();
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
    await act(async () => {
      await client.refetchQueries({ queryKey });
    });
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Powiąż płatność" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(post.mock.calls[2]).toEqual(post.mock.calls[0]);
    expect(
      post.mock.calls.every(
        ([url]) => url === `/finance/bills/${bill.id}/allocations`,
      ),
    ).toBe(true);
  });
});

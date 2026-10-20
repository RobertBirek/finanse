import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TransactionSearch } from "./TransactionSearch";
import {
  parseSearchAmount,
  transactionSearchParams,
} from "../../lib/transactionSearch";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useTransactionSearch: vi.fn(),
  useTransaction: vi.fn(),
}));
vi.mock("../../api/finance", () => ({
  ...hooks,
  useUpdateTransaction: () => ({ mutate: vi.fn() }),
  useDeleteTransaction: () => ({ mutate: vi.fn() }),
}));
const account = {
  id: "account1",
  name: "Eurokonto",
  currency: "EUR",
  is_active: false,
};
const transaction = {
  id: "tx1",
  transaction_date: "2026-10-20",
  description: "Zakup kawy",
  type: "expense",
  source: "manual",
  is_pending: false,
  postings: [
    {
      id: "p1",
      account_id: "account1",
      category_id: null,
      source_currency: "EUR",
      source_amount: 12345,
      base_amount_pln: 54321,
      fx_rate: 4.4,
      direction: "debit",
    },
  ],
};
function Location() {
  const location = useLocation(),
    navigate = useNavigate();
  return (
    <>
      <output aria-label="Adres">{location.search}</output>
      <button onClick={() => navigate(-1)}>Wstecz przeglądarki</button>
    </>
  );
}
function mount(url = "/finances/transactions") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <TransactionSearch />
      <Location />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  hooks.useAccounts.mockReturnValue({ data: [account], refetch: vi.fn() });
  hooks.useCategories.mockReturnValue({
    data: [{ id: "cat1", name: "Jedzenie", is_active: false }],
    refetch: vi.fn(),
  });
  hooks.useTransactionSearch.mockImplementation((p) => ({
    data: { items: [transaction], total: 53, limit: p.limit, offset: p.offset },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }));
  hooks.useTransaction.mockReturnValue({
    data: transaction,
    isLoading: false,
    isError: false,
  });
});

describe("search filters and amounts", () => {
  it.each([
    ["0", 0],
    ["1,01", 101],
    ["1234.56", 123456],
    ["0.29", 29],
    ["", undefined],
  ])("parses %s exactly to minor units", (text, amount) =>
    expect(parseSearchAmount(String(text))).toBe(amount),
  );
  it.each(["-1", "1.001", "NaN", "Infinity", "1e3", "90071992547410"])(
    "rejects invalid or unsafe amount %s",
    (text) => expect(() => parseSearchAmount(text)).toThrow(),
  );
  it.each([
    "min=20&max=10",
    "date_from=2026-11-01&date_to=2026-01-01",
    "date_from=2026-02-30",
    "page=-1",
    "size=500",
    "page=99999999",
  ])("validates URL %s", (url) =>
    expect(() => transactionSearchParams(new URLSearchParams(url))).toThrow(),
  );
});

describe("complete transaction history", () => {
  it("submits all filters to the server and resets pagination", () => {
    mount("/finances/transactions?page=3");
    fireEvent.change(
      screen.getByLabelText("Szukaj po opisie, koncie lub kategorii"),
      { target: { value: "Kawa" } },
    );
    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "account1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "cat1" },
    });
    fireEvent.change(screen.getByLabelText("Waluta źródłowa"), {
      target: { value: "EUR" },
    });
    fireEvent.change(screen.getByLabelText("Kwota od (PLN)"), {
      target: { value: "123,45" },
    });
    fireEvent.change(screen.getByLabelText("Data od"), {
      target: { value: "2026-10-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zastosuj filtry" }));
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        q: "Kawa",
        account_id: "account1",
        category_id: "cat1",
        currency: "EUR",
        min_amount_pln: 12345,
        date_from: "2026-10-01",
        offset: 0,
      }),
      true,
    );
  });
  it("keeps URL filters/page through detail, close and browser Back", () => {
    mount("/finances/transactions?q=Kawa&currency=EUR&page=2");
    expect(screen.getByText("Wyniki 26–26 z 53")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Szczegóły: Zakup kawy" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Szczegóły transakcji" });
    expect(within(dialog).getByText("123,45 EUR")).toBeInTheDocument();
    expect(within(dialog).getByText("543,21 PLN")).toBeInTheDocument();
    expect(within(dialog).getByText("4.4")).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Zamknij szczegóły" }),
    );
    expect(screen.getByLabelText("Adres").textContent).toContain("page=2");
    fireEvent.click(screen.getByRole("button", { name: "Następna" }));
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "Kawa", currency: "EUR", offset: 50 }),
      true,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Wstecz przeglądarki" }),
    );
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 25 }),
      true,
    );
  });
  it("restores account selection even when account options arrive after URL hydration", () => {
    hooks.useAccounts.mockReturnValue({ data: [], refetch: vi.fn() });
    const view = mount("/finances/transactions?account_id=account1");
    hooks.useAccounts.mockReturnValue({ data: [account], refetch: vi.fn() });
    view.rerender(
      <MemoryRouter
        initialEntries={["/finances/transactions?account_id=account1"]}
      >
        <TransactionSearch />
        <Location />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("Konto")).toHaveValue("account1");
  });
  it("retains filters on error rather than presenting an empty history", () => {
    hooks.useTransactionSearch.mockReturnValue({
      isError: true,
      refetch: vi.fn(),
    });
    mount("/finances/transactions?q=Kawa");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Nie udało się wyszukać transakcji",
    );
    expect(
      screen.getByLabelText("Szukaj po opisie, koncie lub kategorii"),
    ).toHaveValue("Kawa");
    expect(
      screen.queryByText(/Brak transakcji spełniających/),
    ).not.toBeInTheDocument();
  });
  it("clears invalid filters and requests the first page", () => {
    mount("/finances/transactions?min=10&max=1&page=2");
    expect(screen.getByRole("alert")).toHaveTextContent("Kwota od");
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.anything(),
      false,
    );
    fireEvent.click(screen.getByRole("button", { name: "Wyczyść filtry" }));
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        offset: 0,
        min_amount_pln: undefined,
        max_amount_pln: undefined,
      }),
      true,
    );
  });
  it("preserves a draft filter while opening and closing details", () => {
    mount("/finances/transactions?q=Kawa");
    const input = screen.getByLabelText(
      "Szukaj po opisie, koncie lub kategorii",
    );
    fireEvent.change(input, { target: { value: "Robocza fraza" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Szczegóły: Zakup kawy" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Zamknij szczegóły" }));
    expect(
      screen.getByLabelText("Szukaj po opisie, koncie lub kategorii"),
    ).toHaveValue("Robocza fraza");
  });
  it("does not discard a selected account if names cannot be loaded", () => {
    hooks.useAccounts.mockReturnValue({ data: [], refetch: vi.fn() });
    mount("/finances/transactions?account_id=account1");
    fireEvent.click(screen.getByRole("button", { name: "Zastosuj filtry" }));
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ account_id: "account1" }),
      true,
    );
  });
  it("closes a direct detail link without navigating outside the app", () => {
    mount("/finances/transactions?q=Kawa&page=2&detail=tx1");
    fireEvent.click(screen.getByRole("button", { name: "Zamknij szczegóły" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Adres").textContent).toContain("page=2");
    expect(screen.getByLabelText("Adres").textContent).not.toContain("detail=");
  });
  it("offers recovery when deletion leaves a page empty", () => {
    hooks.useTransactionSearch.mockReturnValue({
      data: { items: [], total: 25, limit: 25, offset: 25 },
    });
    mount("/finances/transactions?page=2");
    expect(screen.getByText(/Ta strona jest już pusta/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Następna" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Pierwsza strona" }));
    expect(hooks.useTransactionSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 0 }),
      true,
    );
  });
});

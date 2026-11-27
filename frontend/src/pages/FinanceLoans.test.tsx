import {
  fireEvent,
  render as rtlRender,
  screen,
  within,
} from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FinanceLoans } from "./FinanceLoans";
import { FinanceLoanSettings } from "./FinanceLoanSettings";
const render = (element: ReactElement, search = "?loan=loan-1") =>
  rtlRender(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/finances/loans${search}`]}>
        {element}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useAllegroPay: vi.fn(),
  useLoans: vi.fn(),
  useActiveLoanDetails: vi.fn(),
  useCardStatementPlans: vi.fn(),
  useCreditCards: vi.fn(),
  useLoan: vi.fn(),
  useCreateLoan: vi.fn(),
  useCreateLoanInstallment: vi.fn(),
  useUpdateLoanInstallment: vi.fn(),
  useDeleteLoanInstallment: vi.fn(),
  useUpdateLoan: vi.fn(),
  useLoanPaymentCandidates: vi.fn(),
  useLinkLoanPayment: vi.fn(),
  useUnlinkLoanPayment: vi.fn(),
}));

vi.mock("../api/allegroPay", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/allegroPay")>()),
  useAllegroPay: hooks.useAllegroPay,
}));

vi.mock("../api/creditCards", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/creditCards")>()),
  useCreditCards: hooks.useCreditCards,
}));
vi.mock("../api/finance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/finance")>()),
  useAccounts: hooks.useAccounts,
}));
vi.mock("../api/loans", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/loans")>()),
  ...hooks,
}));

const agreement = {
  id: "loan-1",
  name: "Q7",
  account_id: "debt",
  payment_account_id: "bank",
  is_active: true,
  currency: "PLN" as const,
  ledger_balance_pln: -100000,
  planned_principal_pln: 90000,
  planned_interest_pln: 9000,
  planned_fees_pln: 1000,
  total_planned_pln: 100000,
  paid_pln: 40000,
  remaining_pln: 60000,
  requires_accounting_review: true,
};

describe("FinanceLoans", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useAllegroPay.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useCardStatementPlans.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useCreditCards.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useAccounts.mockReturnValue({
      data: [
        {
          id: "debt",
          name: "Kredyt",
          currency: "PLN",
          is_active: true,
          is_budget_account: true,
        },
        {
          id: "bank",
          name: "Rachunek",
          currency: "PLN",
          is_active: true,
          is_budget_account: false,
        },
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useLoans.mockReturnValue({
      data: [agreement],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useActiveLoanDetails.mockReturnValue([]);
    hooks.useLoan.mockReturnValue({
      data: {
        ...agreement,
        installments: [
          {
            id: "i1",
            number: 1,
            due_date: "2026-11-01",
            principal_pln: 90000,
            interest_pln: 9000,
            fees_pln: 1000,
            total_pln: 100000,
            paid_pln: 40000,
            remaining_pln: 60000,
            payment_status: "partial",
            payments: [],
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    for (const key of [
      "useCreateLoan",
      "useCreateLoanInstallment",
      "useUpdateLoanInstallment",
      "useDeleteLoanInstallment",
      "useUpdateLoan",
      "useLinkLoanPayment",
      "useUnlinkLoanPayment",
    ] as const)
      hooks[key].mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
        error: null,
      });
    hooks.useLoanPaymentCandidates.mockReturnValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("selects the first active agreement by default and keeps it selected in the URL", () => {
    render(<FinanceLoans />, "?month=2");
    const tile = screen.getByRole("button", { name: /Umowa aktywna Q7/ });
    expect(tile).toHaveAttribute("aria-pressed", "true");
    expect(hooks.useLoan).toHaveBeenCalledWith("loan-1");
    expect(screen.getByText("Saldo księgowe")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Ustawienia umowy" }),
    ).toHaveAttribute("href", "/settings/finances/loans?loan=loan-1");
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?month=2&loan=loan-1",
    );
  });

  it("does not deselect an explicitly selected archived agreement", () => {
    const archived = {
      ...agreement,
      id: "loan-archived",
      name: "Archiwalna Q7",
      is_active: false,
    };
    hooks.useLoans.mockReturnValue({
      data: [agreement, archived],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoans />, "?loan=loan-archived");
    const archivedTile = screen.getByRole("button", {
      name: /Umowa archiwalna Archiwalna Q7/,
    });
    expect(archivedTile).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(archivedTile);
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?loan=loan-archived",
    );
  });

  it("persists a deselected Allegro tile across a remount without reopening the default loan", () => {
    hooks.useAllegroPay.mockReturnValue({
      data: [
        {
          id: "allegro-1",
          account_id: "account-allegro",
          account_name: "Allegro testowe",
          limit_pln: null,
          ledger_balance_pln: 0,
          available_pln: null,
          scheduled_remaining_pln: 0,
          scheduled_costs_pln: 0,
          purchases: [],
        },
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const view = render(<FinanceLoans />, "?month=2&allegro=allegro-1");
    const tile = screen.getByRole("button", {
      name: /Allegro Pay Allegro testowe/,
    });
    expect(tile).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(tile);
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?month=2&selected=none",
    );
    expect(screen.queryByText("Saldo księgowe")).not.toBeInTheDocument();
    view.unmount();
    render(<FinanceLoans />, "?month=2&selected=none");
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?month=2&selected=none",
    );
    expect(screen.queryByText("Saldo księgowe")).not.toBeInTheDocument();
  });

  it("treats only selected=none as a collapsed URL state and clears it when a loan is selected", () => {
    render(<FinanceLoans />, "?month=2&selected=none");
    expect(screen.queryByText("Saldo księgowe")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Umowa aktywna Q7/ }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?month=2&loan=loan-1",
    );
  });

  it("does not treat an unknown selected marker as a collapsed state", () => {
    render(<FinanceLoans />, "?month=2&selected=unexpected");
    expect(screen.getByText("Saldo księgowe")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(
      "?month=2&loan=loan-1",
    );
  });

  it("shows the operational 30-day overview", () => {
    render(<FinanceLoans />);
    expect(
      screen.getByRole("heading", { name: "Nadchodzące raty (30 dni)" }),
    ).toBeInTheDocument();
  });

  it("does not claim there are no upcoming installments while the loan list loads", () => {
    hooks.useLoans.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoans />);
    expect(
      within(
        screen.getByRole("region", { name: "Nadchodzące raty" }),
      ).getByRole("status"),
    ).toHaveTextContent("Ładowanie umów");
    expect(
      screen.queryByText(/Brak niepokrytych rat z terminem/),
    ).not.toBeInTheDocument();
  });

  it("does not claim there are no upcoming installments when the loan list fails", () => {
    hooks.useLoans.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });
    render(<FinanceLoans />);
    expect(
      within(
        screen.getByRole("region", { name: "Nadchodzące raty" }),
      ).getByRole("alert"),
    ).toHaveTextContent("Nie udało się pobrać umów");
    expect(
      screen.queryByText(/Brak niepokrytych rat z terminem/),
    ).not.toBeInTheDocument();
  });

  it("uses local calendar dates for the upcoming horizon", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-15T22:30:00.000Z"));
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(-120);
    hooks.useActiveLoanDetails.mockReturnValue([
      {
        data: {
          ...agreement,
          installments: [
            {
              id: "previous-local-day",
              number: 1,
              due_date: "2026-08-15",
              principal_pln: 50000,
              interest_pln: 0,
              fees_pln: 0,
              total_pln: 50000,
              paid_pln: 0,
              remaining_pln: 50000,
              payment_status: "unpaid",
              payments: [],
            },
          ],
        },
        isLoading: false,
        isError: false,
      },
    ]);
    render(<FinanceLoans />);
    expect(screen.queryByText(/Q7.*rata 1/)).not.toBeInTheDocument();
  });

  it("keeps available upcoming installments visible when another active schedule fails", () => {
    hooks.useActiveLoanDetails.mockReturnValue([
      {
        data: {
          ...agreement,
          installments: [
            {
              id: "upcoming",
              number: 2,
              due_date: new Date(Date.now() + 24 * 60 * 60 * 1000)
                .toISOString()
                .slice(0, 10),
              principal_pln: 50000,
              interest_pln: 0,
              fees_pln: 0,
              total_pln: 50000,
              paid_pln: 0,
              remaining_pln: 50000,
              payment_status: "unpaid",
              payments: [],
            },
          ],
        },
        isLoading: false,
        isError: false,
      },
      { data: undefined, isLoading: false, isError: true },
    ]);
    render(<FinanceLoans />);
    expect(screen.getByText(/Q7.*rata 2/)).toBeInTheDocument();
    expect(
      screen.getByText(/Widoczne pozycje mogą być niepełne/),
    ).toHaveAttribute("role", "alert");
  });

  it("does not replace a failed active schedule with an empty upcoming state", () => {
    hooks.useActiveLoanDetails.mockReturnValue([
      { data: undefined, isLoading: false, isError: true },
    ]);
    render(<FinanceLoans />);
    expect(
      screen.getByText(/Widoczne pozycje mogą być niepełne/),
    ).toHaveAttribute("role", "alert");
    expect(
      screen.queryByText(/Brak niepokrytych rat z terminem/),
    ).not.toBeInTheDocument();
  });

  it("keeps linking payments available from the operational detail", () => {
    render(<FinanceLoans />);
    expect(
      screen.getByRole("button", { name: "Powiąż płatność" }),
    ).toBeEnabled();
  });

  it("shows partial status and never treats raw ledger balance as remaining principal", () => {
    render(<FinanceLoans />);
    expect(screen.getAllByText("Częściowo pokryta")).not.toHaveLength(0);
    expect(screen.getByText("Saldo księgowe")).toBeInTheDocument();
    expect(screen.getByText("Do pokrycia w harmonogramie")).toBeInTheDocument();
    expect(screen.getByText(/Plan ≠ wykonana płatność/)).toBeInTheDocument();
  });

  it("offers import for this agreement and distinguishes bank numbering while preserving payments", () => {
    const current = hooks.useLoan().data;
    hooks.useLoan.mockReturnValue({
      data: {
        ...current,
        active_schedule_revision_id: "bank-version",
        installments: [
          {
            ...current.installments[0],
            number: 45,
            bank_number: 1,
            schedule_revision_id: "bank-version",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoanSettings />);
    expect(
      screen.getByRole("link", { name: "Importuj harmonogram" }),
    ).toHaveAttribute(
      "href",
      "/finances/imports?kind=loan_schedule&loan=loan-1",
    );
    expect(screen.getByText(/numer bankowy w wersji: 1/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Dodaj ratę" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edytuj ratę" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Powiąż płatność" }),
    ).not.toBeInTheDocument();
  });

  it("creates an agreement in settings and opens its details", () => {
    const mutate = vi.fn((_payload, options) =>
      options.onSuccess({ id: "new-loan" }),
    );
    hooks.useCreateLoan.mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    });
    render(<FinanceLoanSettings />);
    const agreementForm = screen.getByRole("form", { name: "Nowa umowa" });
    expect(agreementForm.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(
      agreementForm.closest("details")!.querySelector("summary")!,
    );
    fireEvent.change(screen.getByLabelText("Nazwa"), {
      target: { value: "Nowy kredyt" },
    });
    fireEvent.change(screen.getByLabelText("Konto zadłużenia"), {
      target: { value: "debt" },
    });
    fireEvent.change(screen.getByLabelText("Rachunek spłaty"), {
      target: { value: "bank" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj umowę" }));
    expect(mutate).toHaveBeenCalledWith(
      { name: "Nowy kredyt", account_id: "debt", payment_account_id: "bank" },
      expect.anything(),
    );
    expect(hooks.useLoan).toHaveBeenLastCalledWith("new-loan");
  });

  it("keeps manual installment creation collapsed in settings", () => {
    render(<FinanceLoanSettings />);
    const installmentForm = screen.getByRole("form", { name: "Nowa rata" });
    expect(installmentForm.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Dodaj ratę ręcznie"));
    expect(installmentForm.closest("details")).toHaveAttribute("open");
  });

  it("preserves the selected agreement when returning from settings to operations", () => {
    render(<FinanceLoanSettings />);
    expect(
      screen.getByRole("link", { name: "Przejdź do kredytów i pożyczek" }),
    ).toHaveAttribute("href", "/finances/loans?loan=loan-1");
  });

  it("shows an unavailable selection and lets the user recover with an available agreement", () => {
    render(<FinanceLoanSettings />, "?loan=missing");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Wybrana umowa nie jest dostępna.",
    );
    expect(screen.getByRole("combobox", { name: "Umowa" })).toHaveValue("");
    expect(
      screen.getByRole("link", { name: "Przejdź do kredytów i pożyczek" }),
    ).toHaveAttribute("href", "/finances/loans");
    fireEvent.change(screen.getByRole("combobox", { name: "Umowa" }), {
      target: { value: "loan-1" },
    });
    expect(screen.getByTestId("location")).toHaveTextContent("?loan=loan-1");
    expect(screen.getByText("Saldo księgowe")).toBeInTheDocument();
  });

  it("does not label an unresolved loan as unavailable while the loan list loads or fails", () => {
    for (const state of [
      { isLoading: true, isError: false },
      { isLoading: false, isError: true },
    ]) {
      hooks.useLoans.mockReturnValue({
        data: undefined,
        ...state,
        refetch: vi.fn(),
      });
      const view = render(<FinanceLoanSettings />, "?loan=missing");
      expect(
        screen.queryByText("Wybrana umowa nie jest dostępna."),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Przejdź do kredytów i pożyczek" }),
      ).toHaveAttribute("href", "/finances/loans");
      view.unmount();
    }
  });

  it("keeps an archived agreement available through its settings deep link", () => {
    const archived = {
      ...agreement,
      id: "loan-archived",
      name: "Archiwalna Q7",
      is_active: false,
    };
    hooks.useLoans.mockReturnValue({
      data: [agreement, archived],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoanSettings />, "?loan=loan-archived");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Umowa" })).toHaveValue(
      "loan-archived",
    );
    expect(
      screen.getByRole("link", { name: "Przejdź do kredytów i pożyczek" }),
    ).toHaveAttribute("href", "/finances/loans?loan=loan-archived");
  });

  it("filters installments and groups visible results by due year", () => {
    const current = hooks.useLoan().data;
    hooks.useLoan.mockReturnValue({
      data: {
        ...current,
        installments: [
          {
            ...current.installments[0],
            id: "paid",
            due_date: "2025-12-01",
            payment_status: "paid",
          },
          {
            ...current.installments[0],
            id: "partial",
            due_date: "2026-01-01",
            payment_status: "partial",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoanSettings />);
    expect(screen.getByRole("region", { name: "Raty 2025" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Raty 2026" })).toBeVisible();
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), {
      target: { value: "partial" },
    });
    expect(
      screen.queryByRole("region", { name: "Raty 2025" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Raty 2026" })).toBeVisible();
  });

  it("explains when the selected installment status has no matches", () => {
    render(<FinanceLoanSettings />);
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), {
      target: { value: "paid" },
    });
    expect(
      screen.getByText("Brak rat o wybranym statusie."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Brak rat. To nie oznacza, że kredyt został spłacony.",
      ),
    ).not.toBeInTheDocument();
  });

  it("keeps the installment form open after a 409 conflict", () => {
    hooks.useCreateLoanInstallment.mockReturnValue({
      isPending: false,
      error: { response: { status: 409, data: { detail: "Konflikt" } } },
      mutate: vi.fn(),
    });
    render(<FinanceLoanSettings />);
    fireEvent.click(screen.getByRole("button", { name: "Dodaj ratę" }));
    expect(
      screen.getByRole("heading", { name: "Nowa rata" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Konflikt")).toBeInTheDocument();
  });

  it("does not present missing detail data as an empty installment list", () => {
    hooks.useLoan.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<FinanceLoans />);
    expect(
      screen.getByText("Brak danych szczegółowych umowy."),
    ).toBeInTheDocument();
  });

  it("keeps filled installment fields after an asynchronously rejected create", () => {
    hooks.useCreateLoanInstallment.mockReturnValue({
      isPending: false,
      error: null,
      mutate: vi.fn((_payload, options) =>
        options.onError({
          response: { status: 409, data: { detail: "Konflikt raty" } },
        }),
      ),
    });
    render(<FinanceLoanSettings />);
    fireEvent.change(screen.getByLabelText("Numer"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Termin"), {
      target: { value: "2026-12-01" },
    });
    fireEvent.change(screen.getByLabelText("Kapitał (PLN)"), {
      target: { value: "900" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj ratę" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Konflikt raty");
    expect(screen.getByLabelText("Kapitał (PLN)")).toHaveValue("900");
  });

  it("resets the create form after success and when selecting another agreement", () => {
    const secondAgreement = { ...agreement, id: "loan-2", name: "Druga umowa" };
    hooks.useLoans.mockReturnValue({
      data: [agreement, secondAgreement],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    hooks.useCreateLoanInstallment.mockReturnValue({
      isPending: false,
      error: null,
      mutate: vi.fn((_payload, options) => options.onSuccess()),
    });
    render(<FinanceLoanSettings />);
    fireEvent.change(screen.getByLabelText("Numer"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Termin"), {
      target: { value: "2026-12-01" },
    });
    fireEvent.change(screen.getByLabelText("Kapitał (PLN)"), {
      target: { value: "900" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj ratę" }));
    expect(screen.getByLabelText("Kapitał (PLN)")).toHaveValue("0.00");
    fireEvent.change(screen.getByLabelText("Kapitał (PLN)"), {
      target: { value: "800" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Umowa" }), {
      target: { value: "loan-2" },
    });
    expect(screen.getByLabelText("Kapitał (PLN)")).toHaveValue("0.00");
  });

  it("renders mutation errors as alerts for agreement, delete, and unlink actions", () => {
    hooks.useUpdateLoan.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: { response: { data: { detail: "Błąd umowy" } } },
    });
    hooks.useDeleteLoanInstallment.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: { response: { data: { detail: "Błąd usuwania" } } },
    });
    hooks.useUnlinkLoanPayment.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: { response: { data: { detail: "Błąd odpinania" } } },
    });
    render(<FinanceLoanSettings />);
    expect(screen.getByText("Błąd umowy")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Błąd usuwania")).toHaveAttribute("role", "alert");
  });
});

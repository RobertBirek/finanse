import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FinanceLoans } from "./FinanceLoans";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useLoans: vi.fn(),
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
  beforeEach(() => {
    vi.clearAllMocks();
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

  it("shows partial status and never treats raw ledger balance as remaining principal", () => {
    render(<FinanceLoans />);
    expect(screen.getByText("Częściowo pokryta")).toBeInTheDocument();
    expect(screen.getByText("Saldo księgowe")).toBeInTheDocument();
    expect(screen.getByText("Do pokrycia w harmonogramie")).toBeInTheDocument();
    expect(screen.getByText(/Plan ≠ wykonana płatność/)).toBeInTheDocument();
  });

  it("keeps the installment form open after a 409 conflict", () => {
    hooks.useCreateLoanInstallment.mockReturnValue({
      isPending: false,
      error: { response: { status: 409, data: { detail: "Konflikt" } } },
      mutate: vi.fn(),
    });
    render(<FinanceLoans />);
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
    render(<FinanceLoans />);
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
    render(<FinanceLoans />);
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
    fireEvent.click(screen.getByRole("button", { name: /Druga umowa/ }));
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
    render(<FinanceLoans />);
    expect(screen.getByText("Błąd umowy")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Błąd usuwania")).toHaveAttribute("role", "alert");
  });
});

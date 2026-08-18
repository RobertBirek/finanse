import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FinanceAccounts } from "./FinanceAccounts";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCreateAccount: vi.fn(),
  useUpdateAccount: vi.fn(),
  useDeleteAccount: vi.fn(),
  useCreateCategory: vi.fn(),
  useUpdateCategory: vi.fn(),
  useDeleteCategory: vi.fn(),
}));

vi.mock("../api/finance", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/finance")>();
  return { ...original, ...hooks };
});

const accounts = [
  {
    id: "a1",
    name: "Rachunek główny",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 100000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "a2",
    name: "Lokata",
    type: "savings",
    currency: "EUR",
    is_active: false,
    is_budget_account: false,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

const categories = [
  {
    id: "c1",
    name: "Dom",
    parent_id: null,
    type: "expense",
    is_active: true,
  },
  {
    id: "c2",
    name: "Czynsz",
    parent_id: "c1",
    type: "expense",
    is_active: false,
  },
  {
    id: "c3",
    name: "Wynagrodzenie",
    parent_id: null,
    type: "income",
    is_active: true,
  },
];

function createAccountForm() {
  return within(screen.getByRole("form", { name: "Nowe konto" }));
}

function createCategoryForm() {
  return within(screen.getByRole("form", { name: "Nowa kategoria" }));
}

describe("FinanceAccounts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useAccounts.mockReturnValue({
      data: accounts,
      isLoading: false,
      isError: false,
    });
    hooks.useCategories.mockReturnValue({
      data: categories,
      isLoading: false,
      isError: false,
    });
    hooks.useCreateAccount.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useUpdateAccount.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useDeleteAccount.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useCreateCategory.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useUpdateCategory.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useDeleteCategory.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renderuje sekcje Konta i Kategorie z pozycjami", () => {
    render(<FinanceAccounts />);

    expect(
      screen.getByRole("heading", { name: "Konta i kategorie" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Konta" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Kategorie" }),
    ).toBeInTheDocument();

    expect(screen.getByText("Rachunek główny")).toBeInTheDocument();
    expect(screen.getByText("Bieżące · PLN")).toBeInTheDocument();
    expect(screen.getByText("Lokata")).toBeInTheDocument();
    expect(screen.getByText("Oszczędnościowe · EUR")).toBeInTheDocument();
    expect(screen.getByText("budżetowe")).toBeInTheDocument();

    expect(screen.getAllByText("Dom").length).toBeGreaterThan(0);
    expect(screen.getByText("Wydatek · —")).toBeInTheDocument();
    expect(screen.getAllByText("Czynsz").length).toBeGreaterThan(0);
    expect(screen.getByText("Wydatek · Dom")).toBeInTheDocument();
    expect(screen.getAllByText("Wynagrodzenie").length).toBeGreaterThan(0);
    expect(screen.getByText("Przychód · —")).toBeInTheDocument();
  });

  it("nieaktywne konto ma badge nieaktywne i jest wygaszone", () => {
    render(<FinanceAccounts />);

    expect(screen.getByText("nieaktywne")).toBeInTheDocument();

    const lokataRow = screen
      .getByRole("button", { name: "Aktywuj konto Lokata" })
      .closest("div.rounded-lg");
    expect(lokataRow).not.toBeNull();
    expect(lokataRow).toHaveClass("opacity-60");
  });

  it("utworzenie konta wywołuje useCreateAccount.mutate z {name,type,currency}", () => {
    const createMutate = vi.fn();
    hooks.useCreateAccount.mockReturnValue({
      mutate: createMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.change(createAccountForm().getByLabelText("Nazwa"), {
      target: { value: "Testowe" },
    });
    fireEvent.change(createAccountForm().getByLabelText("Typ"), {
      target: { value: "cash" },
    });
    fireEvent.change(createAccountForm().getByLabelText("Waluta"), {
      target: { value: "EUR" },
    });
    fireEvent.click(
      createAccountForm().getByRole("button", { name: "Dodaj konto" }),
    );

    expect(createMutate).toHaveBeenCalledTimes(1);
    expect(createMutate.mock.calls[0][0]).toEqual({
      name: "Testowe",
      type: "cash",
      currency: "EUR",
    });

    act(() => {
      (createMutate.mock.calls[0][1] as { onSuccess: () => void }).onSuccess();
    });

    expect(createAccountForm().getByLabelText("Nazwa")).toHaveValue("");
    expect(createAccountForm().getByLabelText("Waluta")).toHaveValue("PLN");
  });

  it("odznaczenie budżetowego przy tworzeniu wysyła is_budget_account: false", () => {
    const createMutate = vi.fn();
    hooks.useCreateAccount.mockReturnValue({
      mutate: createMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.change(createAccountForm().getByLabelText("Nazwa"), {
      target: { value: "Portfel" },
    });
    fireEvent.click(createAccountForm().getByLabelText("Konto budżetowe"));
    fireEvent.click(
      createAccountForm().getByRole("button", { name: "Dodaj konto" }),
    );

    expect(createMutate.mock.calls[0][0]).toEqual({
      name: "Portfel",
      type: "checking",
      currency: "PLN",
      is_budget_account: false,
    });
  });

  it("wyłącza przycisk Dodaj konto podczas trwającej mutacji", () => {
    hooks.useCreateAccount.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      error: null,
    });

    render(<FinanceAccounts />);

    expect(
      createAccountForm().getByRole("button", { name: "Dodaj konto" }),
    ).toBeDisabled();
  });

  it("przełącznik aktywności wywołuje useUpdateAccount.mutate z is_active", () => {
    const updateMutate = vi.fn();
    hooks.useUpdateAccount.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Dezaktywuj konto Rachunek główny",
      }),
    );

    expect(updateMutate).toHaveBeenCalledTimes(1);
    expect(updateMutate.mock.calls[0][0]).toEqual({
      id: "a1",
      is_active: false,
    });
  });

  it("edycja konta wywołuje useUpdateAccount.mutate z {id,name,type,is_budget_account}", () => {
    const updateMutate = vi.fn();
    hooks.useUpdateAccount.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj konto Rachunek główny" }),
    );

    const row = screen
      .getByRole("button", { name: "Zapisz konto Rachunek główny" })
      .closest("div.rounded-lg");
    expect(row).not.toBeNull();

    fireEvent.change(within(row as HTMLElement).getByLabelText("Nazwa"), {
      target: { value: "Główne v2" },
    });
    fireEvent.change(within(row as HTMLElement).getByLabelText("Typ"), {
      target: { value: "cash" },
    });
    fireEvent.click(within(row as HTMLElement).getByLabelText("Budżetowe"));
    fireEvent.click(
      screen.getByRole("button", { name: "Zapisz konto Rachunek główny" }),
    );

    expect(updateMutate).toHaveBeenCalledTimes(1);
    expect(updateMutate.mock.calls[0][0]).toEqual({
      id: "a1",
      name: "Główne v2",
      type: "cash",
      is_budget_account: false,
    });
  });

  it("usunięcie konta wywołuje useDeleteAccount.mutate po potwierdzeniu", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteMutate = vi.fn();
    hooks.useDeleteAccount.mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Usuń konto Rachunek główny" }),
    );

    expect(confirmSpy).toHaveBeenCalledWith('Usunąć konto "Rachunek główny"?');
    expect(deleteMutate).toHaveBeenCalledTimes(1);
    expect(deleteMutate.mock.calls[0][0]).toBe("a1");
  });

  it("nie usuwa konta bez potwierdzenia", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const deleteMutate = vi.fn();
    hooks.useDeleteAccount.mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Usuń konto Rachunek główny" }),
    );

    expect(deleteMutate).not.toHaveBeenCalled();
  });

  it("błąd 409 przy usuwaniu konta pokazuje komunikat inline", () => {
    hooks.useDeleteAccount.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: {
        response: {
          status: 409,
          data: {
            detail: "Account has records; deactivate it instead of deleting",
          },
        },
      },
      variables: "a1",
    });

    render(<FinanceAccounts />);

    expect(
      screen.getByText("Konto ma zapisy — zdezaktywuj je zamiast usuwać"),
    ).toBeInTheDocument();
  });

  it("błąd 409 przy usuwaniu kategorii pokazuje komunikat inline", () => {
    hooks.useDeleteCategory.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: {
        response: { status: 409, data: { detail: "Category has records" } },
      },
      variables: "c1",
    });

    render(<FinanceAccounts />);

    expect(
      screen.getByText("Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać"),
    ).toBeInTheDocument();
  });

  it("edycja kategorii wywołuje useUpdateCategory.mutate", () => {
    const updateCategoryMutate = vi.fn();
    hooks.useUpdateCategory.mockReturnValue({
      mutate: updateCategoryMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj kategorię Czynsz" }),
    );

    const row = screen
      .getByRole("button", { name: "Zapisz kategorię Czynsz" })
      .closest("div.rounded-lg");
    expect(row).not.toBeNull();

    fireEvent.change(within(row as HTMLElement).getByLabelText("Nazwa"), {
      target: { value: "Czynsz v2" },
    });
    fireEvent.change(
      within(row as HTMLElement).getByLabelText("Kategoria nadrzędna"),
      { target: { value: "" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Zapisz kategorię Czynsz" }),
    );

    expect(updateCategoryMutate).toHaveBeenCalledTimes(1);
    expect(updateCategoryMutate.mock.calls[0][0]).toEqual({
      id: "c2",
      name: "Czynsz v2",
      type: "expense",
      parent_id: null,
    });
  });

  it("dodanie kategorii wywołuje useCreateCategory.mutate", () => {
    const createCategoryMutate = vi.fn();
    hooks.useCreateCategory.mockReturnValue({
      mutate: createCategoryMutate,
      isPending: false,
      error: null,
    });

    render(<FinanceAccounts />);

    fireEvent.change(createCategoryForm().getByLabelText("Nazwa"), {
      target: { value: "Paliwo" },
    });
    fireEvent.change(createCategoryForm().getByLabelText("Typ"), {
      target: { value: "expense" },
    });
    fireEvent.click(
      createCategoryForm().getByRole("button", { name: "Dodaj kategorię" }),
    );

    expect(createCategoryMutate).toHaveBeenCalledTimes(1);
    expect(createCategoryMutate.mock.calls[0][0]).toEqual({
      name: "Paliwo",
      type: "expense",
    });

    fireEvent.change(
      createCategoryForm().getByLabelText("Kategoria nadrzędna"),
      { target: { value: "c1" } },
    );
    fireEvent.click(
      createCategoryForm().getByRole("button", { name: "Dodaj kategorię" }),
    );

    expect(createCategoryMutate.mock.calls[1][0]).toEqual({
      name: "Paliwo",
      type: "expense",
      parent_id: "c1",
    });
  });
});

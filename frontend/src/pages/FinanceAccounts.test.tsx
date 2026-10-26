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
  {
    id: "c4",
    name: "Prąd",
    parent_id: "c2",
    type: "expense",
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

    const tree = screen.getByRole("list", { name: "Drzewo kategorii" });
    expect(within(tree).getByText("Dom")).toBeInTheDocument();
    expect(within(tree).getByText("Czynsz")).toBeInTheDocument();
    expect(within(tree).getByText("Prąd")).toBeInTheDocument();
    expect(within(tree).getByText(/archiwalna/)).toBeInTheDocument();
    expect(within(tree).getByText("Wynagrodzenie")).toBeInTheDocument();
  });

  it("drzewo zachowuje aktywnego potomka archiwalnej kategorii i pozwala je zwinąć", () => {
    render(<FinanceAccounts />);

    expect(screen.getByText("Prąd")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Zwiń Dom" }));
    expect(screen.queryByText("Czynsz")).not.toBeInTheDocument();
    expect(screen.queryByText("Prąd")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rozwiń Dom" }));
    expect(screen.getByText("Prąd")).toBeVisible();
  });

  it("archiwizuje i przywraca kategorię zamiast usuwać ją z drzewa", () => {
    const updateCategoryMutate = vi.fn();
    hooks.useUpdateCategory.mockReturnValue({
      mutate: updateCategoryMutate,
      isPending: false,
      error: null,
    });
    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Dezaktywuj kategorię Dom" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Aktywuj kategorię Czynsz" }),
    );

    expect(updateCategoryMutate).toHaveBeenNthCalledWith(1, {
      id: "c1",
      is_active: false,
    });
    expect(updateCategoryMutate).toHaveBeenNthCalledWith(2, {
      id: "c2",
      is_active: true,
    });
  });

  it.each([
    {
      response: {
        status: 422,
        data: { detail: [{ msg: "Invalid", loc: ["body", "name"] }] },
      },
    },
    { response: { status: 500, data: { detail: { message: "Unexpected" } } } },
    new Error("Network Error"),
  ])(
    "shows a safe message for structured and network errors without crashing",
    (error) => {
      hooks.useCreateAccount.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
        error,
      });
      render(<FinanceAccounts />);
      expect(
        screen.getByText(
          "Nie udało się zapisać zmian. Sprawdź dane i spróbuj ponownie.",
        ),
      ).toBeInTheDocument();
      expect(
        createAccountForm().getByRole("button", { name: "Dodaj konto" }),
      ).toBeEnabled();
    },
  );

  it("preserves a textual API error for the category form", () => {
    hooks.useCreateCategory.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: {
        response: {
          data: { detail: "Parent category type must match category type" },
        },
      },
    });
    render(<FinanceAccounts />);
    expect(
      createCategoryForm().getByText(
        "Parent category type must match category type",
      ),
    ).toBeInTheDocument();
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
      .closest("li");
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

  it("dodanie podkategorii wybiera rodzica i zgodny typ w formularzu", () => {
    render(<FinanceAccounts />);

    fireEvent.click(
      screen.getByRole("button", { name: "Dodaj podkategorię do Dom" }),
    );

    expect(
      createCategoryForm().getByLabelText("Kategoria nadrzędna"),
    ).toHaveValue("c1");
    expect(createCategoryForm().getByLabelText("Typ")).toHaveValue("expense");
  });

  it("maskuje IBAN, pozwala go pokazać/skopiować i wysyła null przy wyczyszczeniu metadanych", () => {
    const updateMutate = vi.fn();
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    hooks.useAccounts.mockReturnValue({
      data: [
        {
          ...accounts[0],
          iban: "PL12 3456 7890 1234",
          bank_name: "Bank testowy",
          account_holder: "Anna",
          bic: "TESTPLPW",
          notes: "konto domowe",
        },
      ],
      isLoading: false,
      isError: false,
    });
    hooks.useUpdateAccount.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
    });
    render(<FinanceAccounts />);

    expect(screen.getByText("•••• 1234")).toBeInTheDocument();
    expect(screen.queryByText("PL12 3456 7890 1234")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pokaż" }));
    expect(screen.getByText("PL12 3456 7890 1234")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));
    expect(writeText).toHaveBeenCalledWith("PL12 3456 7890 1234");

    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj konto Rachunek główny" }),
    );
    const editingRow = screen
      .getByRole("button", { name: "Zapisz konto Rachunek główny" })
      .closest("div.rounded-lg")!;
    fireEvent.change(
      within(editingRow as HTMLElement).getByLabelText("IBAN / NRB"),
      {
        target: { value: "" },
      },
    );
    fireEvent.click(screen.getByText("Pozostałe dane bankowe"));
    for (const label of [
      "Bank / instytucja",
      "Właściciel rachunku",
      "BIC / SWIFT",
      "Notatka",
    ]) {
      fireEvent.change(
        within(editingRow as HTMLElement).getByLabelText(label),
        { target: { value: "" } },
      );
    }
    fireEvent.click(
      screen.getByRole("button", { name: "Zapisz konto Rachunek główny" }),
    );

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "a1",
        iban: null,
        bank_name: null,
        account_holder: null,
        bic: null,
        notes: null,
      }),
      expect.any(Object),
    );
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

  it("nie pokazuje danych rachunku bankowego dla nowego konta gotówkowego", () => {
    render(<FinanceAccounts section="accounts" />);
    fireEvent.change(createAccountForm().getByLabelText("Typ"), {
      target: { value: "cash" },
    });
    expect(
      createAccountForm().queryByText("Dane bankowe (opcjonalne)"),
    ).not.toBeInTheDocument();
  });
});

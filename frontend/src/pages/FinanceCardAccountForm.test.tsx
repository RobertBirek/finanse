import { fireEvent, render, screen, within } from "@testing-library/react";
import { Link, MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { FinanceAccounts } from "./FinanceAccounts";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCreateAccount: vi.fn(),
  useUpdateAccount: vi.fn(),
  useDeleteAccount: vi.fn(),
  useCreateCategory: vi.fn(),
}));
vi.mock("../api/finance", async (original) => ({
  ...(await original<typeof import("../api/finance")>()),
  ...hooks,
}));
const terms = {
  limit_pln: 2500000,
  apr: "12.5000",
  cycle_close_day: 20,
  due_day: 15,
  grace_days: 54,
  version: 3,
};
const account = {
  id: "card-a",
  name: "Pierwsza karta",
  type: "credit_card",
  currency: "PLN",
  is_active: true,
  is_budget_account: true,
  balance_pln: -10000,
  opened_at: "2026-01-01",
  closed_at: null,
  credit_card: terms,
};
const create = vi.fn();
const update = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  hooks.useAccounts.mockReturnValue({
    data: [account, { ...account, id: "card-b", name: "Druga karta" }],
    isLoading: false,
    isError: false,
  });
  hooks.useCategories.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  hooks.useCreateAccount.mockReturnValue({
    mutate: create,
    isPending: false,
    error: null,
  });
  hooks.useUpdateAccount.mockReturnValue({
    mutate: update,
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
});
function open(path = "/settings/finances/accounts") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FinanceAccounts section="accounts" />
    </MemoryRouter>,
  );
}
function fillTerms(form: ReturnType<typeof within>) {
  for (const [label, value] of [
    ["Limit PLN", "18000,50"],
    ["Oprocentowanie roczne %", "9,25"],
    ["Dzień zamknięcia cyklu", "17"],
    ["Domyślny dzień spłaty", "12"],
    ["Maksymalny okres bezodsetkowy (dni)", "57"],
  ]) {
    fireEvent.change(form.getByLabelText(label), { target: { value } });
  }
}

it("creates the credit-card account and its validated settings in one request", () => {
  open();
  const form = within(screen.getByRole("form", { name: "Nowe konto" }));
  expect(
    form.getByRole("option", { name: "Karta kredytowa" }),
  ).toBeInTheDocument();
  expect(form.queryByLabelText("Limit PLN")).not.toBeInTheDocument();
  fireEvent.change(form.getByLabelText("Typ"), {
    target: { value: "credit_card" },
  });
  fireEvent.change(form.getByLabelText("Nazwa"), {
    target: { value: "Trzecia karta" },
  });
  expect(form.getByLabelText("Waluta")).toBeDisabled();
  expect(form.getByLabelText("Waluta")).toHaveValue("PLN");
  fillTerms(form);
  fireEvent.submit(screen.getByRole("form", { name: "Nowe konto" }));
  expect(create).toHaveBeenCalledTimes(1);
  expect(create.mock.calls[0][0]).toMatchObject({
    name: "Trzecia karta",
    type: "credit_card",
    currency: "PLN",
    credit_card: {
      limit_pln: 1800050,
      apr: "9.25",
      cycle_close_day: 17,
      due_day: 12,
      grace_days: 57,
      expected_version: 0,
    },
  });
});

it("edits the requested account with server terms and version without touching another card", () => {
  open("/settings/finances/accounts?edit=card-a");
  expect(screen.getByLabelText("Limit PLN")).toHaveValue("25000");
  fireEvent.change(screen.getByLabelText("Limit PLN"), {
    target: { value: "27000" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Zapisz konto Pierwsza karta" }),
  );
  expect(update).toHaveBeenCalledTimes(1);
  expect(update.mock.calls[0][0]).toMatchObject({
    id: "card-a",
    credit_card: {
      apr: "12.5000",
      cycle_close_day: 20,
      due_day: 15,
      grace_days: 54,
      expected_version: 3,
      limit_pln: 2700000,
    },
  });
  expect(update.mock.calls[0][0].credit_card).not.toHaveProperty("version");
});

it("omits unchanged card settings when only the name changes", () => {
  open("/settings/finances/accounts?edit=card-a");
  const input = screen.getByDisplayValue("Pierwsza karta");
  fireEvent.change(input, { target: { value: "Nowa nazwa" } });
  fireEvent.click(
    screen.getByRole("button", { name: "Zapisz konto Pierwsza karta" }),
  );
  expect(update.mock.calls[0][0]).not.toHaveProperty("credit_card");
});

it("refuses incomplete or out-of-range settings instead of sending a partial account", () => {
  open();
  const element = screen.getByRole("form", { name: "Nowe konto" });
  const form = within(element);
  fireEvent.change(form.getByLabelText("Typ"), {
    target: { value: "credit_card" },
  });
  fireEvent.change(form.getByLabelText("Nazwa"), {
    target: { value: "Incomplete" },
  });
  fireEvent.submit(element);
  expect(create).not.toHaveBeenCalled();
  expect(form.getByRole("alert")).toHaveTextContent(/warunki|limit/i);
  fillTerms(form);
  fireEvent.change(form.getByLabelText("Dzień zamknięcia cyklu"), {
    target: { value: "32" },
  });
  fireEvent.submit(element);
  expect(create).not.toHaveBeenCalled();
});

it("keeps an unsuccessful edit open and restores saved values after cancel/reopen", () => {
  hooks.useUpdateAccount.mockReturnValue({
    mutate: update,
    isPending: false,
    error: {
      response: { status: 409, data: { detail: "Odśwież warunki karty" } },
    },
    variables: { id: "card-a" },
  });
  open("/settings/finances/accounts?edit=card-a");
  fireEvent.change(screen.getByLabelText("Limit PLN"), {
    target: { value: "28000" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Zapisz konto Pierwsza karta" }),
  );
  expect(screen.getByLabelText("Limit PLN")).toHaveValue("28000");
  fireEvent.click(
    screen.getByRole("button", { name: "Anuluj edycję konta Pierwsza karta" }),
  );
  expect(screen.queryByLabelText("Limit PLN")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Edytuj konto Pierwsza karta" }),
  );
  expect(screen.getByLabelText("Limit PLN")).toHaveValue("25000");
});

it("follows an account edit URL change instead of retaining the previously selected card", () => {
  render(
    <MemoryRouter initialEntries={["/settings/finances/accounts"]}>
      <Link to="/settings/finances/accounts?edit=card-b">
        Otwórz drugą kartę
      </Link>
      <FinanceAccounts section="accounts" />
    </MemoryRouter>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Edytuj konto Pierwsza karta" }),
  );
  fireEvent.change(screen.getByLabelText("Limit PLN"), {
    target: { value: "29000" },
  });
  fireEvent.click(screen.getByRole("link", { name: "Otwórz drugą kartę" }));
  expect(
    screen.getByRole("button", { name: "Zapisz konto Druga karta" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Zapisz konto Pierwsza karta" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Limit PLN")).toHaveValue("25000");
});

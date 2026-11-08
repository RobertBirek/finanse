import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { FinanceCreditCards } from "./FinanceCreditCards";

const hooks = vi.hoisted(() => ({
  useCreditCards: vi.fn(),
  useCreditCard: vi.fn(),
  useAccounts: vi.fn(),
}));
vi.mock("../api/creditCards", async (original) => ({
  ...(await original<typeof import("../api/creditCards")>()),
  useCreditCards: hooks.useCreditCards,
  useCreditCard: hooks.useCreditCard,
}));
vi.mock("../api/finance", async (original) => ({
  ...(await original<typeof import("../api/finance")>()),
  useAccounts: hooks.useAccounts,
}));
const first = {
  account_id: "first",
  name: "Pierwsza karta",
  is_active: true,
  color: "#123456",
  configured: true,
  limit_pln: 2000000,
  debt_pln: 120000,
  available_pln: 1850000,
  pending_debits_pln: 30000,
  overpayment_pln: 0,
  overlimit_pln: 0,
};
beforeEach(() => {
  vi.clearAllMocks();
  hooks.useCreditCards.mockReturnValue({
    data: [
      first,
      {
        ...first,
        account_id: "second",
        name: "Druga karta",
        is_active: false,
        limit_pln: 900000,
        debt_pln: 0,
        available_pln: 900000,
      },
    ],
    isLoading: false,
    isError: false,
  });
  hooks.useAccounts.mockReturnValue({
    data: [{ id: "checking", name: "Zwykły rachunek", currency: "PLN" }],
    isError: false,
  });
  hooks.useCreditCard.mockReturnValue({ data: null });
});
function Detail() {
  return <p>Szczegóły {useParams().accountId}</p>;
}
function open(path = "/settings/finances/cards") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/settings/finances/cards"
          element={<FinanceCreditCards />}
        />
        <Route
          path="/settings/finances/cards/:accountId"
          element={<Detail />}
        />
      </Routes>
    </MemoryRouter>,
  );
}
it("shows each card with its own current position using only the summary endpoint", () => {
  open();
  const one = within(screen.getByRole("article", { name: "Pierwsza karta" }));
  const two = within(screen.getByRole("article", { name: "Druga karta" }));
  expect(one.getByText(/20\s?000,00/)).toBeInTheDocument();
  expect(one.getByText(/1\s?200,00/)).toBeInTheDocument();
  expect(one.getByText(/18\s?500,00/)).toBeInTheDocument();
  expect(two.getByText(/Nieaktywna/)).toBeInTheDocument();
  expect(screen.queryByText("Zwykły rachunek")).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  expect(hooks.useAccounts).not.toHaveBeenCalled();
  expect(hooks.useCreditCard).not.toHaveBeenCalled();
  expect(one.getByRole("link", { name: "Wyciągi i raty" })).toHaveAttribute(
    "href",
    "/settings/finances/cards/first",
  );
  expect(one.getByRole("link", { name: "Edytuj konto" })).toHaveAttribute(
    "href",
    "/settings/finances/accounts?edit=first",
  );
  expect(two.getByRole("link", { name: "Edytuj konto" })).toHaveAttribute(
    "href",
    "/settings/finances/accounts?edit=second",
  );
});
it("offers account configuration when there are no cards without a card creation form", () => {
  hooks.useCreditCards.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  open();
  expect(screen.getByText(/Brak kart kredytowych/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Przejdź do kont" })).toHaveAttribute(
    "href",
    "/settings/finances/accounts",
  );
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
});
it("does not display an error or a missing configuration as zero available credit", () => {
  hooks.useCreditCards.mockReturnValue({
    data: [
      { ...first, configured: false, limit_pln: null, available_pln: null },
    ],
    isLoading: false,
    isError: false,
  });
  const view = open();
  expect(screen.getByText(/Uzupełnij warunki/)).toBeInTheDocument();
  expect(screen.queryByText(/^0,00 PLN$/)).not.toBeInTheDocument();
  view.unmount();
  hooks.useCreditCards.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
  });
  open();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Nie udało się pobrać kart",
  );
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
it("shows loading separately from an empty list", () => {
  hooks.useCreditCards.mockReturnValue({
    data: undefined,
    isLoading: true,
    isError: false,
  });
  open();
  expect(screen.getByRole("status")).toHaveTextContent(/Ładowanie/);
  expect(screen.queryByText(/Brak kart/)).not.toBeInTheDocument();
});
it("keeps old account query links usable through the new detail route", () => {
  open("/settings/finances/cards?account=second");
  expect(screen.getByText("Szczegóły second")).toBeInTheDocument();
});

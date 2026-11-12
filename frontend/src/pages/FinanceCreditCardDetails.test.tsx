import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { FinanceCreditCardDetails } from "./FinanceCreditCardDetails";
import { categorySelectFixture } from "../test/categoryFixtures";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCreditCard: vi.fn(),
  useCardMutation: vi.fn(),
  useCardCandidates: vi.fn(),
}));
vi.mock("../api/finance", async (original) => ({
  ...(await original<typeof import("../api/finance")>()),
  useAccounts: hooks.useAccounts,
  useCategories: hooks.useCategories,
}));
vi.mock("../api/creditCards", () => ({
  useCreditCard: hooks.useCreditCard,
  useCardMutation: hooks.useCardMutation,
  useCardCandidates: hooks.useCardCandidates,
}));

const mutateAsync = vi.fn();
const card = {
  account_id: "card",
  limit_pln: 3360000,
  apr: "14.5000",
  cycle_close_day: 17,
  due_day: 12,
  grace_days: 57,
  version: 1,
  debt_pln: 102796,
  available_pln: 3257204,
  pending_debits_pln: 0,
  overpayment_pln: 0,
  overlimit_pln: 0,
  plans: [],
  allocations: [],
  charges: [],
  statements: [
    {
      id: "s1",
      period_end: "2026-09-17",
      due_date: "2026-10-13",
      debt_pln: 1315866,
      minimum_pln: 27350,
      remaining_pln: 1315866,
      minimum_remaining_pln: 27350,
      reconciliation_difference_pln: 0,
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  hooks.useAccounts.mockReturnValue({
    data: [
      {
        id: "card",
        name: "VELOBANK - karta",
        currency: "PLN",
        is_active: true,
      },
    ],
    isLoading: false,
    isError: false,
  });
  hooks.useCategories.mockReturnValue({
    data: [
      { id: "expense", name: "Odsetki", type: "expense", is_active: true },
    ],
    isError: false,
  });
  hooks.useCreditCard.mockReturnValue({
    data: card,
    isLoading: false,
    isError: false,
  });
  hooks.useCardMutation.mockReturnValue({ mutateAsync, isPending: false });
  hooks.useCardCandidates.mockReturnValue({
    data: {
      items: [
        {
          id: "purchase",
          description: "Zakup",
          amount_pln: 100000,
          date: "2026-10-01",
        },
      ],
      total: 1,
    },
    isLoading: false,
    isError: false,
  });
  mutateAsync.mockResolvedValue({});
});

function openCard() {
  render(
    <MemoryRouter initialEntries={["/settings/finances/cards/card"]}>
      <Routes>
        <Route
          path="/settings/finances/cards/:accountId"
          element={<FinanceCreditCardDetails />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

it("uses sorted full expense category names for card charges", () => {
  hooks.useCategories.mockReturnValue({ data: categorySelectFixture });
  openCard();
  fireEvent.change(screen.getByLabelText("Sposób zapisania kosztu"), {
    target: { value: "new" },
  });
  const select = screen.getByLabelText("Kategoria kosztu");
  expect(
    within(select)
      .getAllByRole("option")
      .slice(1)
      .map((option) => option.textContent),
  ).toEqual(["Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
});

it("opens bank import for the current card without creating another card account", () => {
  openCard();
  expect(
    screen.getByRole("link", { name: "Importuj wyciąg karty" }),
  ).toHaveAttribute("href", "/finances/imports?account=card");
  expect(mutateAsync).not.toHaveBeenCalled();
});

it("shows current credit position separately from historical statement debt", () => {
  openCard();
  expect(
    within(
      screen.getByRole("region", { name: "Wykorzystanie limitu" }),
    ).getByText(/1\s?027,96/),
  ).toBeInTheDocument();
  expect(screen.getByText("2026-10-13")).toBeInTheDocument();
  expect(
    within(
      screen.getByRole("region", { name: "Wykorzystanie limitu" }),
    ).getByText(/Maksymalny okres bezodsetkowy/),
  ).toHaveTextContent("57");
  expect(screen.getByText(/warunków banku/)).toBeInTheDocument();
});

it("does not render failure as an unconfigured card or a zero balance", () => {
  hooks.useCreditCard.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
  });
  openCard();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Nie udało się pobrać karty",
  );
  expect(
    screen.queryByRole("region", { name: "Wykorzystanie limitu" }),
  ).not.toBeInTheDocument();
});

it("directs an unconfigured card to account editing without a second configuration form", () => {
  hooks.useCreditCard.mockReturnValue({
    data: null,
    isLoading: false,
    isError: false,
  });
  openCard();
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  expect(screen.getByText(/Uzupełnij warunki/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Edytuj konto" })).toHaveAttribute(
    "href",
    "/settings/finances/accounts?edit=card",
  );
  expect(mutateAsync).not.toHaveBeenCalled();
});

it("submits a plan with its own APR and existing purchase without posting another expense", async () => {
  openCard();
  const form = screen.getByRole("form", { name: "Nowy plan ratalny" });
  for (const [label, value] of [
    ["Nazwa planu", "Nowy Komfort"],
    ["Kapitał PLN", "1000"],
    ["Oprocentowanie planu %", "8.25"],
    ["Liczba rat", "10"],
    ["Pierwsza rata", "2026-12-12"],
    ["Prowizja PLN", "0"],
    ["Transakcja źródłowa", "purchase"],
  ])
    fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.submit(form);
  await vi.waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        apr: "8.25",
        principal_pln: 100000,
        source_transaction_id: "purchase",
        count: 10,
      }),
    ),
  );
});

it("retains a failed plan and the request key on an identical retry", async () => {
  mutateAsync.mockRejectedValue(new Error("conflict"));
  openCard();
  const form = screen.getByRole("form", { name: "Nowy plan ratalny" });
  for (const [label, value] of [
    ["Nazwa planu", "Komfort"],
    ["Kapitał PLN", "1000"],
    ["Oprocentowanie planu %", "8.25"],
    ["Liczba rat", "10"],
    ["Pierwsza rata", "2026-12-12"],
    ["Prowizja PLN", "0"],
    ["Transakcja źródłowa", "purchase"],
  ])
    fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.submit(form);
  await screen.findByText(/Nie udało się zapisać/);
  expect(within(form).getByLabelText("Nazwa planu")).toHaveValue("Komfort");
  const first = mutateAsync.mock.calls[0][0];
  fireEvent.submit(form);
  await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
  expect(mutateAsync.mock.calls[1][0].request_id).toBe(first.request_id);
});

it("requires an explicit choice between booking a new cost and linking one", () => {
  openCard();
  expect(
    screen.queryByRole("form", { name: "Odsetki, opłaty i korekty" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Sposób zapisania kosztu"), {
    target: { value: "link" },
  });
  const form = screen.getByRole("form", { name: "Odsetki, opłaty i korekty" });
  expect(
    within(form).getByLabelText("Istniejąca transakcja kosztu"),
  ).toBeRequired();
});

it("shows an explicit interest estimate separately without booking it", async () => {
  mutateAsync.mockResolvedValueOnce({ estimated_interest_pln: 1192 });
  openCard();
  const form = screen.getByRole("form", { name: "Szacunek odsetek" });
  fireEvent.change(within(form).getByLabelText("Oprocentowany kapitał PLN"), {
    target: { value: "1000" },
  });
  fireEvent.change(within(form).getByLabelText("Liczba dni"), {
    target: { value: "30" },
  });
  fireEvent.submit(form);
  expect(await screen.findByText(/11,92 PLN/)).toHaveTextContent("Szacunek");
  expect(mutateAsync.mock.calls[0][0]).toEqual({
    principal_pln: 100000,
    apr: "14.5000",
    days: 30,
  });
});

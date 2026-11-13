import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { FinancePeople } from "./FinancePeople";
import { FinancePersonDetails } from "./FinancePersonDetails";
import { PersonGiftDialog } from "../components/finance/PersonGiftDialog";
import { AccountTransactions } from "../components/finance/AccountTransactions";
import type { Account } from "../api/finance";

const person = {
  id: "person",
  name: "Osoba A",
  is_active: true,
  version: 1,
  reference_account_id: null,
};
const context = {
  transaction_id: "txn",
  snapshot: "a".repeat(64),
  person: null,
  eligible: true,
  reason: null,
};
let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "o@example.test",
      display_name: "Owner",
      is_active: true,
    },
  });
  vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/person-link")
      ? context
      : String(url).endsWith("/summary")
        ? {
            person_id: "person",
            gift_count: 12,
            received_gifts_pln: 123400,
            received_by_currency: { PLN: 123400 },
          }
        : String(url).endsWith("/gifts")
          ? { items: [], total: 0, limit: 50, offset: 0 }
          : String(url).endsWith("/people/person")
            ? person
            : String(url).endsWith("/people")
              ? { items: [person], total: 1, limit: 50, offset: 0 }
              : [],
  }));
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
function show(element: React.ReactNode, route = "/finances/people") {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

it("lists people and creates an identity without ledger fields", async () => {
  const post = vi.spyOn(api, "post").mockResolvedValue({ data: person });
  show(<FinancePeople />);
  expect(await screen.findByRole("link", { name: "Osoba A" })).toHaveAttribute(
    "href",
    "/finances/people/person",
  );
  fireEvent.click(screen.getByRole("button", { name: "Dodaj osobę" }));
  fireEvent.change(await screen.findByLabelText("Nazwa osoby"), {
    target: { value: " Nowa osoba " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz osobę" }));
  await waitFor(() => expect(post).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(post.mock.calls[0][1]).toEqual({
    name: "Nowa osoba",
    reference_account_id: null,
  });
});

it("uses the backend total even when the visible history page is empty", async () => {
  show(
    <Routes>
      <Route
        path="/finances/people/:personId"
        element={<FinancePersonDetails />}
      />
    </Routes>,
    "/finances/people/person",
  );
  expect(await screen.findByText("1234,00 PLN")).toBeVisible();
  expect(screen.getByText(/12 operacji/)).toBeVisible();
  expect(screen.getByText(/Brak przypisanych darowizn/)).toBeVisible();
  expect(screen.queryByText(/Do zwrotu/)).not.toBeInTheDocument();
});

it("assigns only identity and reviewed snapshot, not money", async () => {
  const put = vi
    .spyOn(api, "put")
    .mockResolvedValue({ data: { ...context, person } });
  const close = vi.fn();
  show(<PersonGiftDialog transactionId="txn" onClose={close} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Darczyńca" }), {
    target: { value: "person" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Przypisz darczyńcę" }));
  await waitFor(() => expect(close).toHaveBeenCalled());
  expect(put.mock.calls[0][1]).toEqual({
    person_id: "person",
    expected_transaction_snapshot: context.snapshot,
  });
  expect(put.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toBeTruthy();
});

it("does not auto-reclassify an imported income with an invalid category", async () => {
  vi.mocked(api.get).mockResolvedValue({
    data: {
      ...context,
      eligible: false,
      reason: "Wymagana osobna korekta kategorii.",
    },
  });
  const put = vi.spyOn(api, "put");
  const patch = vi.spyOn(api, "patch");
  show(<PersonGiftDialog transactionId="txn" onClose={vi.fn()} />);
  expect(
    await screen.findByText("Wymagana osobna korekta kategorii."),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Przypisz darczyńcę" }),
  ).not.toBeInTheDocument();
  expect(put).not.toHaveBeenCalled();
  expect(patch).not.toHaveBeenCalled();
});

it("requires explicit refresh after a conflict rather than silently accepting new state", async () => {
  const put = vi.spyOn(api, "put").mockRejectedValue({
    response: { status: 409, data: { detail: "Dane zmieniły się." } },
  });
  show(<PersonGiftDialog transactionId="txn" onClose={vi.fn()} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Darczyńca" }), {
    target: { value: "person" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Przypisz darczyńcę" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Dane zmieniły się.",
  );
  expect(
    screen.getByRole("button", { name: "Przypisz darczyńcę" }),
  ).toBeDisabled();
  expect(put).toHaveBeenCalledTimes(1);
});

it("offers unlink for an already attributed gift without changing the ledger", async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { ...context, person } });
  const detach = vi.spyOn(api, "delete").mockResolvedValue({ data: context });
  show(<PersonGiftDialog transactionId="txn" onClose={vi.fn()} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Odepnij darczyńcę" }),
  );
  await waitFor(() => expect(detach).toHaveBeenCalled());
  expect(detach.mock.calls[0][1]?.data).toEqual({
    expected_transaction_snapshot: context.snapshot,
  });
});

it("archives with an explicit version and keeps history available", async () => {
  const patch = vi
    .spyOn(api, "patch")
    .mockResolvedValue({ data: { ...person, is_active: false, version: 2 } });
  show(
    <Routes>
      <Route
        path="/finances/people/:personId"
        element={<FinancePersonDetails />}
      />
    </Routes>,
    "/finances/people/person",
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Archiwizuj osobę" }),
  );
  await waitFor(() => expect(patch).toHaveBeenCalled());
  expect(patch.mock.calls[0][1]).toEqual({
    expected_version: 1,
    is_active: false,
  });
});

it("reuses the same intent key after an ambiguous network failure", async () => {
  const put = vi.spyOn(api, "put").mockRejectedValue(new Error("network"));
  show(<PersonGiftDialog transactionId="txn" onClose={vi.fn()} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Darczyńca" }), {
    target: { value: "person" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Przypisz darczyńcę" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Przypisz darczyńcę" }));
  await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
  expect(put.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toBe(
    put.mock.calls[1][2]?.headers?.["Idempotency-Key"],
  );
});

it("does not substitute gift totals for the existing informational account balance", async () => {
  const account = {
    id: "account",
    name: "Ewidencja osoby",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: false,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  } as Account;
  show(<AccountTransactions accounts={[account]} />);
  fireEvent.click(screen.getByRole("button", { name: /Ewidencja osoby/ }));
  expect(
    await screen.findByRole("link", { name: "Historia darowizn od tej osoby" }),
  ).toHaveAttribute("href", "/finances/people/person");
  expect(screen.getAllByText("0,00 PLN").length).toBeGreaterThan(0);
  expect(screen.queryByText("1234,00 PLN")).not.toBeInTheDocument();
});

it("does not keep the previous gift draft when another cached transaction opens", async () => {
  const put = vi
    .spyOn(api, "put")
    .mockResolvedValue({
      data: { ...context, transaction_id: "next", person },
    });
  const view = show(<PersonGiftDialog transactionId="txn" onClose={vi.fn()} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Darczyńca" }), {
    target: { value: "person" },
  });
  client.setQueryData(
    [
      "finance",
      "people",
      useAuthStore.getState().sessionVersion,
      "link",
      "next",
    ],
    { ...context, transaction_id: "next", snapshot: "b".repeat(64) },
  );
  view.rerender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PersonGiftDialog transactionId="next" onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("combobox", { name: "Darczyńca" }),
  ).toHaveValue("");
  expect(put).not.toHaveBeenCalled();
});

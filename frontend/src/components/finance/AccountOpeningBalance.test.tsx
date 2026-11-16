import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccountRow } from "./AccountSettingsRow";
import { useAuthStore } from "../../stores/authStore";
import api from "../../lib/api";
import type { Account } from "../../api/finance";
import type { OpeningBalanceView } from "../../api/openingBalances";

vi.mock("../../lib/api", () => ({
  default: { put: vi.fn(), get: vi.fn() },
}));

const opening: OpeningBalanceView = {
  amount_minor: 0,
  date: "2026-01-01",
  fx_rate: null,
  version: 1,
  can_edit: true,
  blocked_reason: null,
};
const account: Account = {
  id: "bo-account",
  name: "Bank BO",
  type: "checking",
  currency: "PLN",
  is_active: true,
  is_budget_account: true,
  balance_pln: 100000,
  opened_at: "2026-01-01",
  closed_at: null,
  opening_balance: opening,
};

function show(value = account) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  const update = vi.fn();
  const result = render(
    <QueryClientProvider client={client}>
      <AccountRow
        account={value}
        editing={false}
        onStartEdit={vi.fn()}
        onCancelEdit={vi.fn()}
        updateMutation={{ mutate: update, isPending: false } as never}
        deleteMutation={{ mutate: vi.fn(), isPending: false } as never}
      />
    </QueryClientProvider>,
  );
  return { ...result, client, update };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({
    user: {
      id: "owner-bo",
      email: "bo@example.test",
      display_name: "BO",
      is_active: true,
    },
    sessionVersion: 100,
  });
});
afterEach(() => useAuthStore.setState({ user: null, sessionVersion: 101 }));

describe("account BO command", () => {
  it("shows BO=0 rather than copying the current account balance", () => {
    show();
    expect(screen.getByText(/BO: 0,00 PLN/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Edytuj BO konta Bank BO" }),
    ).toBeEnabled();
  });
  it("shows the server reason instead of an editor for an account with history", () => {
    show({
      ...account,
      opening_balance: {
        ...opening,
        can_edit: false,
        blocked_reason: "Konto ma inne transakcje.",
      },
    });
    expect(
      screen.queryByRole("button", { name: /Edytuj BO/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Konto ma inne transakcje.")).toBeInTheDocument();
  });
  it("saves only BO, reuses the same key after a lost reply and invalidates ledger views", async () => {
    vi.mocked(api.put)
      .mockRejectedValueOnce(new Error("lost reply"))
      .mockResolvedValueOnce({
        data: { ...opening, amount_minor: -12345, version: 2 },
      });
    const { update, client } = show();
    const invalidated = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj BO konta Bank BO" }),
    );
    fireEvent.change(screen.getByLabelText("Kwota BO (PLN)"), {
      target: { value: "-123,45" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz BO" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Zapisz BO" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2));
    const [first, second] = vi.mocked(api.put).mock.calls;
    expect(first).toEqual(second);
    expect(first[0]).toBe("/finance/accounts/bo-account/opening-balance");
    expect(first[1]).toEqual({
      amount_minor: -12345,
      date: "2026-01-01",
      expected_version: 1,
    });
    expect(first[2]?.headers?.["Idempotency-Key"]).toEqual(expect.any(String));
    expect(update).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Zapisz BO" }),
      ).not.toBeInTheDocument(),
    );
    for (const key of [
      "accounts",
      "transactions",
      "summary",
      "cashflow",
      "credit-card",
      "credit-cards",
    ]) {
      expect(invalidated).toHaveBeenCalledWith({ queryKey: ["finance", key] });
    }
  });
  it("requires a fresh read and confirmation after 409", async () => {
    vi.mocked(api.put)
      .mockRejectedValueOnce({
        response: { status: 409, data: { detail: "Wersja BO zmieniła się." } },
      })
      .mockResolvedValueOnce({ data: { ...opening, version: 3 } });
    vi.mocked(api.get).mockResolvedValue({
      data: { ...account, opening_balance: { ...opening, version: 2 } },
    });
    show();
    fireEvent.click(screen.getByRole("button", { name: /Edytuj BO konta/ }));
    fireEvent.click(screen.getByRole("button", { name: "Zapisz BO" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Zapisz BO" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Odśwież BO" }));
    await screen.findByLabelText("Potwierdzam zmianę bilansu otwarcia");
    expect(screen.getByRole("button", { name: "Zapisz BO" })).toBeDisabled();
    fireEvent.click(
      screen.getByLabelText("Potwierdzam zmianę bilansu otwarcia"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Zapisz BO" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.put).mock.calls[1][1]).toMatchObject({
      expected_version: 2,
    });
    expect(vi.mocked(api.put).mock.calls[1][2]).not.toEqual(
      vi.mocked(api.put).mock.calls[0][2],
    );
  });
  it("prevents direct submit from a stale session", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: /Edytuj BO konta/ }));
    const form = screen.getByRole("form", {
      name: "Bilans otwarcia konta Bank BO",
    });
    act(() => useAuthStore.setState({ sessionVersion: 101 }));
    fireEvent.submit(form);
    expect(api.put).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/Sesja/);
  });
});

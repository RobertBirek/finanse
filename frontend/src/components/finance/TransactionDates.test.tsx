import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { TransactionList } from "./AccountTransactions";
import { TransactionDetail } from "./TransactionDetail";

let client: QueryClient;
const owner = {
  id: "owner",
  email: "owner@example.test",
  display_name: "Owner",
  is_active: true,
};
const txn = {
  id: "date-txn",
  transaction_date: "2026-02-02",
  description: "Synthetic receipt",
  type: "expense" as const,
  is_pending: false,
  source: "manual",
  project_id: null,
  updated_at: "2026-11-03T12:00:00Z",
  postings: [],
};
const meta = {
  purchase_date: "2026-01-30",
  booking_date: "2026-02-02",
  purchase_date_source: "manual" as const,
  booking_date_source: "manual" as const,
  version: 3,
};
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useAuthStore.setState({
    user: owner,
    isAuthenticated: true,
    authStatus: "authenticated",
  });
});
afterEach(() => {
  client.clear();
  vi.restoreAllMocks();
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    authStatus: "unauthenticated",
  });
});

it("labels historical dates unknown rather than claiming bank provenance", () => {
  render(
    <TransactionList transactions={[txn]} loading={false} error={false} />,
    { wrapper },
  );
  expect(screen.getByText(/typ daty nieustalony/i)).toBeInTheDocument();
});

it("same-session auth refresh keeps the reviewed date dialog usable", async () => {
  render(
    <TransactionList
      transactions={[{ ...txn, date_metadata: meta }]}
      loading={false}
      error={false}
    />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Koryguj daty" }));
  vi.spyOn(api, "get").mockResolvedValue({ data: { ...owner } });
  await act(async () => useAuthStore.getState().fetchUser());
  expect(screen.queryByText(/Sesja zmieniła się/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Zapisz daty" })).toBeEnabled();
});

it("shows the same two explicit dates in row and detail", async () => {
  const explicit = { ...txn, date_metadata: meta };
  vi.spyOn(api, "get").mockResolvedValue({ data: explicit });
  const { unmount } = render(
    <TransactionList transactions={[explicit]} loading={false} error={false} />,
    { wrapper },
  );
  expect(screen.getByText(/Zakup:.*30\.01\.2026/)).toBeInTheDocument();
  expect(screen.getByText(/Księgowanie:.*2\.02\.2026/)).toBeInTheDocument();
  unmount();
  render(
    <TransactionDetail
      id={txn.id}
      accounts={[]}
      categories={[]}
      onClose={() => {}}
    />,
    { wrapper },
  );
  await waitFor(() =>
    expect(screen.getByText(/Zakup:.*30\.01\.2026/)).toBeInTheDocument(),
  );
});

it("requires explicit confirmation of an unknown booking date and sends version/snapshot", async () => {
  const patch = vi
    .spyOn(api, "patch")
    .mockResolvedValue({ data: { ...txn, date_metadata: meta } });
  render(
    <TransactionList transactions={[txn]} loading={false} error={false} />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Koryguj daty" }));
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.change(dialog.getByLabelText("Data zakupu"), {
    target: { value: "2026-01-30" },
  });
  expect(dialog.getByRole("button", { name: "Zapisz daty" })).toBeDisabled();
  fireEvent.click(dialog.getByLabelText("Potwierdzam datę księgowania"));
  fireEvent.click(dialog.getByRole("button", { name: "Zapisz daty" }));
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith(
      "/finance/transactions/date-txn/dates",
      expect.objectContaining({
        purchase_date: "2026-01-30",
        booking_date: "2026-02-02",
        expected_version: 0,
        expected_updated_at: txn.updated_at,
      }),
    ),
  );
});

it("preserves entered dates after409 and requires fresh data instead of retrying stale approval", async () => {
  const patch = vi.spyOn(api, "patch").mockRejectedValue({
    response: {
      status: 409,
      data: { code: "date_version_conflict", detail: "Odśwież dane" },
    },
  });
  render(
    <TransactionList
      transactions={[{ ...txn, date_metadata: meta }]}
      loading={false}
      error={false}
    />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Koryguj daty" }));
  fireEvent.change(screen.getByLabelText("Data zakupu"), {
    target: { value: "2026-01-29" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz daty" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Odśwież dane"),
  );
  expect(screen.getByLabelText("Data zakupu")).toHaveValue("2026-01-29");
  expect(screen.getByRole("button", { name: "Zapisz daty" })).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Zamknij i odśwież" }),
  ).toBeInTheDocument();
  expect(patch).toHaveBeenCalledTimes(1);
});

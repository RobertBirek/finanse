import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { TransactionList } from "./AccountTransactions";
import { TransactionDetail } from "./TransactionDetail";

const txn = {
  id: "txn",
  transaction_date: "2026-02-02",
  type: "expense" as const,
  description: "Synthetic purchase",
  source: "manual",
  is_pending: false,
  project_id: null,
  postings: [],
};
const context = {
  transaction_id: "txn",
  eligibility: { allowed: true, reason_code: null, message: null },
  amount_minor: 10000,
  currency: "PLN",
  parts: [{ category_id: "food", amount_minor: 10000 }],
  version: 0,
  source: null,
  context_snapshot: "a".repeat(64),
  max_parts: 50,
};
const cats = [
  {
    id: "food",
    name: "Spożywka",
    type: "expense",
    parent_id: null,
    is_active: true,
  },
  {
    id: "home",
    name: "Chemia",
    type: "expense",
    parent_id: null,
    is_active: true,
  },
];
let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);
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
    data: String(url).endsWith("/categories") ? cats : context,
  }));
});
afterEach(() => {
  client.clear();
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
async function open() {
  render(
    <TransactionList transactions={[txn]} loading={false} error={false} />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Zmień kategorie" }));
  await screen.findByLabelText("Kwota PLN 1");
}
async function split() {
  fireEvent.change(screen.getByLabelText("Kwota PLN 1"), {
    target: { value: "80" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj kategorię" }));
  fireEvent.change(screen.getByLabelText("Kategoria 2"), {
    target: { value: "home" },
  });
  fireEvent.change(screen.getByLabelText("Kwota PLN 2"), {
    target: { value: "20" },
  });
}

it("opens categorization from transaction details without closing the detail context", async () => {
  vi.mocked(api.get).mockImplementation(async (url) => ({
    data: String(url).endsWith("/categories")
      ? cats
      : String(url).endsWith("/txn")
        ? txn
        : context,
  }));
  render(
    <TransactionDetail
      id="txn"
      accounts={[]}
      categories={[]}
      onClose={() => {}}
    />,
    { wrapper },
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Zmień kategorie" }),
  );
  await screen.findByLabelText("Kwota PLN 1");
  expect(
    screen.getByRole("dialog", { name: "Szczegóły transakcji" }),
  ).toBeInTheDocument();
});

it("keeps the approval dialog open on Escape while a confirmed write is pending", async () => {
  let finish!: (value: unknown) => void;
  vi.spyOn(api, "post").mockImplementation(async (url) =>
    String(url).endsWith("/preview")
      ? {
          data: {
            expected_version: 0,
            preview_snapshot: "b".repeat(64),
            before_parts: context.parts,
            after_parts: context.parts,
            target_paths: { food: "Spożywka" },
          },
        }
      : new Promise((resolve) => {
          finish = resolve;
        }),
  );
  await open();
  fireEvent.click(screen.getByRole("button", { name: "Sprawdź podział" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Zatwierdź podział" }),
  );
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  fireEvent(
    screen.getByRole("dialog"),
    new Event("cancel", { bubbles: true, cancelable: true }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await act(async () => finish({ data: { ...context, version: 1 } }));
});
it("requires nonmutating preview and a separate explicit approval for 80/20", async () => {
  const post = vi.spyOn(api, "post").mockImplementation(async (url, data) => ({
    data: String(url).endsWith("/preview")
      ? {
          expected_version: 0,
          preview_snapshot: "b".repeat(64),
          before_parts: context.parts,
          after_parts: (data as { parts: unknown }).parts,
          target_paths: { food: "Spożywka", home: "Chemia" },
        }
      : { ...context, version: 1, source: "manual" },
  }));
  await open();
  await split();
  expect(post).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("button", { name: "Zatwierdź podział" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sprawdź podział" }));
  await screen.findByRole("button", { name: "Zatwierdź podział" });
  expect(
    screen.getByRole("heading", { name: "Przed zmianą" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Po zmianie" }),
  ).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź podział" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/finance/transactions/txn/categorization/apply",
      expect.objectContaining({
        expected_preview_snapshot: "b".repeat(64),
        confirmed: true,
      }),
      expect.objectContaining({
        headers: { "Idempotency-Key": expect.any(String) },
      }),
    ),
  );
});
it("prevents preview when even one grosz is missing and closing does not apply", async () => {
  const post = vi.spyOn(api, "post");
  await open();
  fireEvent.change(screen.getByLabelText("Kwota PLN 1"), {
    target: { value: "99.99" },
  });
  expect(
    screen.getByRole("button", { name: "Sprawdź podział" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Zamknij" }));
  expect(post).not.toHaveBeenCalled();
});
it("retains rows after a stale preview and forbids an automatic fresh approval", async () => {
  vi.spyOn(api, "post").mockRejectedValue({
    response: { status: 409, data: { detail: "Odśwież dane" } },
  });
  await open();
  await split();
  fireEvent.click(screen.getByRole("button", { name: "Sprawdź podział" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Kwota PLN 1")).toHaveValue("80");
  expect(
    screen.getByRole("button", { name: "Sprawdź podział" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Zamknij i odśwież" }),
  ).toBeInTheDocument();
});
it("explains unsupported historical transactions without offering approval", async () => {
  vi.mocked(api.get).mockResolvedValue({
    data: {
      ...context,
      eligibility: {
        allowed: false,
        reason_code: "protected",
        message: "Historia Actual jest chroniona.",
      },
    },
  });
  render(
    <TransactionList transactions={[txn]} loading={false} error={false} />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Zmień kategorie" }));
  await screen.findByText("Historia Actual jest chroniona.");
  expect(
    screen.queryByRole("button", { name: "Sprawdź podział" }),
  ).not.toBeInTheDocument();
});
it("does not invalidate a new session after the old preview completes", async () => {
  let finish!: (result: unknown) => void;
  vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await open();
  fireEvent.click(screen.getByRole("button", { name: "Sprawdź podział" }));
  await waitFor(() => expect(api.post).toHaveBeenCalled());
  act(() =>
    useAuthStore.setState((state) => ({
      sessionVersion: state.sessionVersion + 1,
    })),
  );
  await act(async () =>
    finish({
      data: {
        expected_version: 0,
        preview_snapshot: "b".repeat(64),
        before_parts: context.parts,
        after_parts: context.parts,
        target_paths: { food: "Spożywka" },
      },
    }),
  );
  expect(
    screen.queryByRole("button", { name: "Zatwierdź podział" }),
  ).not.toBeInTheDocument();
});

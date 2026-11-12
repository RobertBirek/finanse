import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { TransactionAnnotationsDialog } from "./TransactionAnnotationsDialog";
import { TransactionList } from "./AccountTransactions";

const context = {
  display_description: null,
  original_description: "[actual:old] Original bank description",
  note: null,
  tags: [],
  project_id: null,
  project_name: null,
  version: 0,
  context_snapshot: "a".repeat(64),
  limits: { display_description: 200, note: 5000, tag_name: 60, tags: 20 },
};
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
    data: String(url).includes("/work/projects")
      ? [{ id: "project", name: "Remont", status: "completed" }]
      : String(url).endsWith("/tags")
        ? [{ id: "existing", name: "Wakacje" }]
        : context,
  }));
});
afterEach(() => {
  client.clear();
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
async function open(onClose = vi.fn()) {
  render(
    <TransactionAnnotationsDialog transactionId="txn" onClose={onClose} />,
    { wrapper },
  );
  return await screen.findByLabelText("Własny opis");
}

it("opens an imported descriptive editor without date account or money inputs", async () => {
  const put = vi.spyOn(api, "put");
  await open();
  expect(screen.getByText(context.original_description)).toBeVisible();
  expect(
    screen.queryByLabelText(/Kwota|Data księgowania|Konto płatności/),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Własny opis")).toHaveAttribute(
    "maxLength",
    "200",
  );
  expect(put).not.toHaveBeenCalled();
});

it("creates and reuses tags locally until Save and writes only the reviewed metadata", async () => {
  const put = vi
    .spyOn(api, "put")
    .mockResolvedValue({ data: { ...context, version: 1 } });
  const close = vi.fn();
  await open(close);
  fireEvent.change(screen.getByLabelText("Własny opis"), {
    target: { value: "Moja nazwa" },
  });
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "Szczegóły zakupu" },
  });
  fireEvent.change(screen.getByLabelText("Nowy tag"), {
    target: { value: "Nowy" },
  });
  fireEvent.keyDown(screen.getByLabelText("Nowy tag"), { key: "Enter" });
  fireEvent.click(
    await screen.findByRole("button", { name: "Dodaj tag Wakacje" }),
  );
  fireEvent.change(screen.getByLabelText("Projekt"), {
    target: { value: "project" },
  });
  expect(put).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await waitFor(() => expect(close).toHaveBeenCalled());
  expect(put.mock.calls[0][1]).toEqual({
    display_description: "Moja nazwa",
    note: "Szczegóły zakupu",
    tags: ["Nowy", "Wakacje"],
    project_id: "project",
    expected_version: 0,
    expected_context_snapshot: "a".repeat(64),
  });
  expect(put.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toBeTruthy();
});

it("cancel does not create tags or edit the source", async () => {
  const put = vi.spyOn(api, "put");
  const close = vi.fn();
  await open(close);
  fireEvent.change(screen.getByLabelText("Nowy tag"), {
    target: { value: "Cancelled" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj tag" }));
  fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
  expect(close).toHaveBeenCalled();
  expect(put).not.toHaveBeenCalled();
});

it("does not dismiss a pending write through the dialog backdrop", async () => {
  let finish!: (value: unknown) => void;
  vi.spyOn(api, "put").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const close = vi.fn();
  await open(close);
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "Pending" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Zapisywanie…" })).toBeDisabled(),
  );
  try {
    fireEvent.click(screen.getByRole("dialog", { name: "Opis i oznaczenia" }));
    expect(close).not.toHaveBeenCalled();
  } finally {
    await act(async () => {
      finish({ data: context });
    });
  }
});

it("409 keeps the draft and requires refresh instead of automatically approving a new version", async () => {
  const put = vi.spyOn(api, "put").mockRejectedValue({
    response: { status: 409, data: { detail: "Dane zmieniły się." } },
  });
  await open();
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "Keep my draft" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Dane zmieniły się.",
  );
  expect(screen.getByLabelText("Notatka")).toHaveValue("Keep my draft");
  expect(
    screen.getByRole("button", { name: "Zapisz oznaczenia" }),
  ).toBeDisabled();
  expect(put).toHaveBeenCalledTimes(1);
});

it("validation errors represented as arrays keep the form and never render server objects", async () => {
  vi.spyOn(api, "put").mockRejectedValue({
    response: {
      status: 422,
      data: {
        detail: [
          { loc: ["body", "note"], msg: "Too long", input: "private input" },
        ],
      },
    },
  });
  await open();
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "Keep after validation" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Nie udało się zapisać oznaczeń",
  );
  expect(screen.getByLabelText("Notatka")).toHaveValue("Keep after validation");
  expect(screen.queryByText("private input")).not.toBeInTheDocument();
});

it("uncertain response retry retains the same idempotency key while a new draft gets a new one", async () => {
  const put = vi.spyOn(api, "put").mockRejectedValue(new Error("network"));
  await open();
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "retry" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
  expect(put.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toEqual(
    put.mock.calls[1][2]?.headers?.["Idempotency-Key"],
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Zapisz oznaczenia" }),
    ).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText("Notatka"), {
    target: { value: "new intent" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await waitFor(() => expect(put).toHaveBeenCalledTimes(3));
  expect(put.mock.calls[0][2]?.headers?.["Idempotency-Key"]).not.toEqual(
    put.mock.calls[2][2]?.headers?.["Idempotency-Key"],
  );
});

it("clear overlay sends null rather than overwriting the original description", async () => {
  const put = vi.spyOn(api, "put").mockResolvedValue({ data: context });
  vi.mocked(api.get).mockImplementation(async (url) => ({
    data: String(url).endsWith("/annotations")
      ? { ...context, display_description: "Old custom", note: "Old note" }
      : [],
  }));
  await open();
  fireEvent.change(screen.getByLabelText("Własny opis"), {
    target: { value: "" },
  });
  fireEvent.change(screen.getByLabelText("Notatka"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz oznaczenia" }));
  await waitFor(() => expect(put).toHaveBeenCalled());
  expect(put.mock.calls[0][1]).toMatchObject({
    display_description: null,
    note: null,
  });
  expect(put.mock.calls[0][1]).not.toHaveProperty("description");
});

it("offers descriptive editing on loans without enabling protected category changes", async () => {
  render(
    <TransactionList
      loading={false}
      error={false}
      transactions={[
        {
          id: "loan",
          description: "Loan payment",
          type: "expense",
          source: "loan_payment",
          is_pending: false,
          project_id: null,
          transaction_date: "2026-02-02",
          postings: [],
        },
      ]}
    />,
    { wrapper },
  );
  fireEvent.click(screen.getByRole("button", { name: "Opis i oznaczenia" }));
  expect(await screen.findByLabelText("Notatka")).toBeVisible();
  const dialog = screen.getByRole("dialog", { name: "Opis i oznaczenia" });
  expect(
    within(dialog).queryByRole("button", { name: "Zmień kategorie" }),
  ).not.toBeInTheDocument();
});

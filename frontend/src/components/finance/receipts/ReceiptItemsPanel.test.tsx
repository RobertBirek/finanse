import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { useAuthStore } from "../../../stores/authStore";
import { ReceiptItemsPanel } from "./ReceiptItemsPanel";
import { context, categories, preview } from "./receiptTestData";
import {
  readContext,
  readJob,
  readResult,
  importPreview,
} from "./receiptReadTestData";

beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({
    sessionVersion: 42,
    user: {
      id: "owner",
      email: "test@example.invalid",
      display_name: "Test",
      is_active: true,
    },
    authStatus: "authenticated",
  });
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReceiptItemsPanel billId="bill" onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}
function reads() {
  return vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/categories")
      ? categories
      : String(url).includes("receipt-stores")
        ? {
            items: [
              {
                id: "store",
                name: "Sklep osiedlowy",
                version: 1,
                active: true,
              },
            ],
            next_cursor: null,
          }
        : String(url).endsWith("/payment")
          ? { allowed: true, blocked_reason: null, last_application: null }
          : context(),
  }));
}

it("explicit_import_still_requires_two_financial_confirmations", async () => {
  const initial = context();
  let current = initial;
  const get = vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/categories")
      ? categories
      : String(url).includes("receipt-stores")
        ? { items: [], next_cursor: null }
        : String(url).endsWith("/payment")
          ? { allowed: true, last_application: null }
          : String(url).endsWith("/reads/context")
            ? readContext
            : String(url).endsWith("/reads")
              ? {
                  items: [{ ...readJob, state: "succeeded" }],
                  next_cursor: null,
                }
              : String(url).endsWith("/result")
                ? readResult
                : String(url).includes("/reads/")
                  ? {
                      ...readJob,
                      state: "succeeded",
                      can_cancel: false,
                      poll_after_ms: null,
                    }
                  : current,
  }));
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("read-import-preview"))
      return { data: importPreview };
    current = structuredClone(context(2));
    current.draft!.body.lines[0].name = "Imported milk";
    return { data: current };
  });
  mount();
  const input = await screen.findByLabelText("Produkt 1");
  fireEvent.change(input, { target: { value: "Mój niezapisany" } });
  fireEvent.click(await screen.findByRole("button", { name: /Próba 1/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Użyj w szkicu" }));
  await screen.findByRole("button", { name: "Zastąp szkic odczytem" });
  expect(input).toHaveValue("Mój niezapisany");
  expect(input).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "Zastąp szkic odczytem" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Produkt 1")).toHaveValue("Imported milk"),
  );
  expect(get).toHaveBeenCalled();
  expect(
    post.mock.calls.filter(
      (c) =>
        String(c[0]).endsWith("/approve") ||
        String(c[0]).endsWith("payment-apply"),
    ),
  ).toHaveLength(0);
});
it("preserves dirty products through query refetch and same-session auth refresh", async () => {
  reads();
  const view = mount();
  const input = await screen.findByLabelText("Produkt 1");
  fireEvent.change(input, { target: { value: "Mój produkt" } });
  await act(async () => {
    await view.client.invalidateQueries({
      queryKey: ["finance", "receipt-items"],
    });
    useAuthStore.setState({ authStatus: "authenticated" });
  });
  expect(input).toHaveValue("Mój produkt");
});
it("an uncertain draft save locks edits and repeats the exact body/key", async () => {
  reads();
  const post = vi
    .spyOn(api, "post")
    .mockRejectedValueOnce(new Error("Disconnected"))
    .mockResolvedValue({ data: context(2) });
  mount();
  await screen.findByLabelText("Produkt 1");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz robocze" }));
  const retry = await screen.findByRole("button", {
    name: "Ponów tę samą operację",
  });
  expect(screen.getByLabelText("Produkt 1")).toBeDisabled();
  fireEvent.click(retry);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0]).toEqual(post.mock.calls[1]);
  expect(post.mock.calls[0][1]).toMatchObject({
    expected_version: 1,
    body: { lines: [{ amount_minor: 8000 }, { amount_minor: 2000 }] },
  });
});
it("item approval never applies the split until a separate preview and confirmation", async () => {
  const get = reads();
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("/approve")) {
      get.mockImplementation(async (u) => ({
        data: String(u).endsWith("/categories")
          ? categories
          : String(u).includes("receipt-stores")
            ? { items: [], next_cursor: null }
            : String(u).endsWith("/payment")
              ? { allowed: true, last_application: null }
              : context(2, true),
      }));
      return { data: context(2, true) };
    }
    if (String(url).endsWith("/payment-preview")) return { data: preview };
    return {
      data: { receipt_id: "r", state_version: 3, revision_id: "approved" },
    };
  });
  mount();
  await screen.findByLabelText("Produkt 1");
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź pozycje" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  fireEvent.click(
    await screen.findByRole("button", { name: "Sprawdź podział płatności" }),
  );
  const confirm = await screen.findByRole("button", {
    name: "Zatwierdź podział",
  });
  expect(
    post.mock.calls.filter((c) => String(c[0]).endsWith("/payment-apply")),
  ).toHaveLength(0);
  fireEvent.click(confirm);
  await waitFor(() =>
    expect(
      post.mock.calls.filter((c) => String(c[0]).endsWith("/payment-apply")),
    ).toHaveLength(1),
  );
});
it("session replacement blocks writes from the old editor", async () => {
  reads();
  const post = vi.spyOn(api, "post");
  mount();
  await screen.findByLabelText("Produkt 1");
  const oldSave = screen.getByRole("button", { name: "Zapisz robocze" });
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
  });
  expect(oldSave).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

it("a historical command replay never reinstalls its old revision as the current editable state", async () => {
  const get = reads();
  const latest = context(4);
  latest.draft!.body = {
    ...latest.draft!.body,
    lines: latest.draft!.body.lines.map((l) => ({
      ...l,
      name: l.line_key === "a" ? "Nowszy zapis w innej karcie" : l.name,
    })),
  };
  vi.spyOn(api, "post").mockImplementation(async () => {
    get.mockImplementation(async (url) => ({
      data: String(url).endsWith("/categories")
        ? categories
        : String(url).includes("receipt-stores")
          ? { items: [], next_cursor: null }
          : String(url).endsWith("/payment")
            ? { allowed: true, last_application: null }
            : latest,
    }));
    return { data: context(2) };
  });
  mount();
  await screen.findByLabelText("Produkt 1");
  fireEvent.click(screen.getByRole("button", { name: "Zapisz robocze" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Produkt 1")).toHaveValue(
      "Nowszy zapis w innej karcie",
    ),
  );
});

it("deleting a product with discount shares is blocked until explicitly reassigned", async () => {
  reads();
  mount();
  await screen.findByLabelText("Produkt 1");
  fireEvent.click(screen.getByRole("button", { name: "Usuń produkt 1" }));
  expect(screen.getByLabelText("Produkt 1")).toHaveValue("Mleko");
  expect(
    screen.getByText(
      "Najpierw usuń lub przenieś udziały rabatu tego produktu.",
    ),
  ).toBeInTheDocument();
});

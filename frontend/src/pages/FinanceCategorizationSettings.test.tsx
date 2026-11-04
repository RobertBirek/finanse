import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../App";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";

vi.mock("../components/Layout", async () => {
  const { Outlet } = await import("react-router-dom");
  return { Layout: () => <Outlet /> };
});
vi.mock("./Today", () => ({ Today: () => <p>Dzisiaj</p> }));

const categories = [
  {
    id: "marker",
    name: "Do opisania",
    type: "expense",
    parent_id: null,
    is_active: true,
  },
  {
    id: "home",
    name: "Dom",
    type: "expense",
    parent_id: null,
    is_active: true,
  },
];
const base = {
  id: "r1",
  version: 1,
  state: "draft",
  display_description: "  CZYNSZ   mieszkanie ",
  normalized_description_exact: "czynsz mieszkanie",
  target_category_id: "home",
  approved_version: null,
};
let policy = {
  version: 0,
  uncategorized_category_id: null as string | null,
  rules_enabled: false,
  max_description_chars: 500,
};
let rules: Record<string, unknown>[];
const clients: QueryClient[] = [];
const auth = useAuthStore.getState();
beforeEach(() => {
  policy = {
    version: 0,
    uncategorized_category_id: null,
    rules_enabled: false,
    max_description_chars: 500,
  };
  rules = [];
  useAuthStore.setState({
    user: {
      id: "u1",
      email: "u@example.com",
      display_name: "User",
      is_active: true,
    },
    authStatus: "authenticated",
    isLoading: false,
    fetchUser: vi.fn(async () => {}),
  });
  vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: url.endsWith("/categories")
      ? categories
      : url.endsWith("/settings")
        ? { ...policy }
        : url.endsWith("/rules")
          ? [...rules]
          : { events: [], poll_after_ms: 2000 },
  }));
  vi.spyOn(api, "patch").mockImplementation(async (_url, body) => {
    const input = body as Record<string, unknown>;
    policy = {
      ...policy,
      version: policy.version + 1,
      uncategorized_category_id: input.uncategorized_category_id as
        string | null,
      rules_enabled: input.rules_enabled as boolean,
    };
    return { data: { ...policy } };
  });
  vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (url.endsWith("/preview"))
      return {
        data: {
          preview_snapshot: "a".repeat(64),
          grant: {
            ...base,
            marker_id: "marker",
            target_path: "Dom",
            scope: "future_manual_pln_only",
          },
        },
      };
    if (url.endsWith("/approve")) {
      rules = [{ ...base, state: "active", approved_version: 1 }];
      return { data: rules[0] };
    }
    rules = [{ ...base }];
    return { data: { ...base } };
  });
});
afterEach(() => {
  cleanup();
  clients.forEach((c) => c.clear());
  clients.length = 0;
  vi.restoreAllMocks();
  useAuthStore.setState(auth);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/settings/finances/categorization"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
it("offers explicit marker settings, initially disabled, with no historical action", async () => {
  mount();
  expect(
    await screen.findByRole("heading", { name: "Kategoryzacja" }),
  ).toBeInTheDocument();
  expect(await screen.findByLabelText("Kategoria techniczna")).toHaveValue("");
  expect(screen.getByLabelText("Włącz zatwierdzone reguły")).not.toBeChecked();
  expect(
    screen.queryByRole("button", { name: /histori/i }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Kategoria techniczna"), {
    target: { value: "marker" },
  });
  fireEvent.click(screen.getByLabelText("Włącz zatwierdzone reguły"));
  expect(
    screen.getByRole("button", { name: "Zapisz ustawienia" }),
  ).toBeDisabled();
  fireEvent.click(
    screen.getByLabelText(/Potwierdzam zakres przyszłych wydatków/),
  );
  fireEvent.click(screen.getByRole("button", { name: "Zapisz ustawienia" }));
  await waitFor(() =>
    expect(api.patch).toHaveBeenCalledWith(
      "/finance/categorization/settings",
      expect.objectContaining({
        uncategorized_category_id: "marker",
        rules_enabled: true,
        confirm_future_only: true,
        expected_version: 0,
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": expect.any(String),
        }),
      }),
    ),
  );
});
it("requires a saved draft and reviewed exact matcher before future-only approval", async () => {
  policy = {
    ...policy,
    version: 1,
    uncategorized_category_id: "marker",
    rules_enabled: true,
  };
  mount();
  await screen.findByRole("heading", { name: "Kategoryzacja" });
  await screen.findByLabelText("Kategoria techniczna");
  fireEvent.click(screen.getByRole("button", { name: "Nowa reguła" }));
  fireEvent.change(screen.getByLabelText("Dokładny opis transakcji"), {
    target: { value: base.display_description },
  });
  fireEvent.change(screen.getByLabelText("Kategoria docelowa"), {
    target: { value: "home" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz szkic" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Podgląd reguły" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Podgląd reguły" }));
  expect(await screen.findByText("czynsz mieszkanie")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Zatwierdź dla przyszłych wydatków" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/Zatwierdzam dokładne dopasowanie/));
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź dla przyszłych wydatków" }),
  );
  await waitFor(() =>
    expect(api.post).toHaveBeenCalledWith(
      "/finance/categorization/rules/r1/approve",
      expect.objectContaining({
        preview_snapshot: "a".repeat(64),
        expected_version: 1,
        confirm_future_only: true,
      }),
      expect.anything(),
    ),
  );
});
it("keeps settings inputs and requires refresh after a stale version", async () => {
  vi.mocked(api.patch).mockRejectedValue({
    response: { status: 409, data: { detail: "Ustawienia zmieniły się." } },
  });
  mount();
  await screen.findByRole("heading", { name: "Kategoryzacja" });
  await screen.findByLabelText("Kategoria techniczna");
  fireEvent.change(screen.getByLabelText("Kategoria techniczna"), {
    target: { value: "marker" },
  });
  fireEvent.click(
    screen.getByLabelText(/Potwierdzam zakres przyszłych wydatków/),
  );
  fireEvent.click(screen.getByRole("button", { name: "Zapisz ustawienia" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Ustawienia zmieniły się.",
  );
  expect(screen.getByLabelText("Kategoria techniczna")).toHaveValue("marker");
  expect(
    screen.getByRole("button", { name: "Zapisz ustawienia" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Wczytaj aktualną wersję" }),
  ).toBeEnabled();
});
it("does not invalidate or announce an old-session save", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(api.patch).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const client = mount();
  await screen.findByRole("heading", { name: "Kategoryzacja" });
  await screen.findByLabelText("Kategoria techniczna");
  fireEvent.click(
    screen.getByLabelText(/Potwierdzam zakres przyszłych wydatków/),
  );
  fireEvent.click(screen.getByRole("button", { name: "Zapisz ustawienia" }));
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  const invalidate = vi.spyOn(client, "invalidateQueries");
  act(() =>
    useAuthStore.setState((s) => ({ sessionVersion: s.sessionVersion + 1 })),
  );
  await act(async () => {
    finish({ data: { ...policy, version: 1 } });
  });
  expect(invalidate).not.toHaveBeenCalled();
  expect(screen.queryByText("Ustawienia zapisane.")).not.toBeInTheDocument();
});

it("keeps marker fields editable after a validation error, not an uncertain network outcome", async () => {
  vi.mocked(api.patch).mockRejectedValue({
    response: { status: 422, data: { detail: "Wybierz aktywną kategorię." } },
  });
  mount();
  await screen.findByLabelText("Kategoria techniczna");
  fireEvent.click(
    screen.getByLabelText(/Potwierdzam zakres przyszłych wydatków/),
  );
  fireEvent.click(screen.getByRole("button", { name: "Zapisz ustawienia" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Kategoria techniczna")).toBeEnabled();
});

it("retries uncertain approval with the same key without permitting a different draft write", async () => {
  policy = {
    ...policy,
    version: 1,
    uncategorized_category_id: "marker",
    rules_enabled: true,
  };
  rules = [{ ...base }];
  const original = vi.mocked(api.post).getMockImplementation()!;
  vi.mocked(api.post).mockImplementation(async (...args) => {
    if (args[0].endsWith("/approve")) throw new Error("network timeout");
    return original(...args);
  });
  mount();
  await screen.findByLabelText("Kategoria techniczna");
  fireEvent.click(
    await screen.findByRole("button", { name: "Edytuj / sprawdź" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Podgląd reguły" }));
  await screen.findByText("czynsz mieszkanie");
  fireEvent.click(screen.getByLabelText(/Zatwierdzam dokładne dopasowanie/));
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź dla przyszłych wydatków" }),
  );
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Zapisz szkic" })).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź dla przyszłych wydatków" }),
  );
  await waitFor(() =>
    expect(
      vi.mocked(api.post).mock.calls.filter((c) => c[0].endsWith("/approve")),
    ).toHaveLength(2),
  );
  const calls = vi
    .mocked(api.post)
    .mock.calls.filter((c) => c[0].endsWith("/approve"));
  expect(calls[0][2]).toEqual(calls[1][2]);
});

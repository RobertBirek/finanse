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
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { ProposalReview } from "./ProposalReview";
import type { ProposalDetail } from "../../api/categoryProposals";

export const item = (id: string): ProposalDetail => ({
  id,
  version: 1,
  status: "pending",
  transaction_id: `txn-${id}`,
  description: `Wydatek ${id}`,
  amount_minor: 10000,
  currency: "PLN",
  decision: "existing_category",
  explanation: "Opis pasuje do domu",
  confidence: "high",
  new_category: null,
  current_parts: [{ category_id: "marker", amount_minor: 10000 }],
  target_path: "Dom / Czynsz",
  eligible: true,
  blocked_reason: null,
  expires_at: "2026-11-11T12:00:00Z",
});
const preview = (id: string) => ({
  proposal_id: id,
  expected_version: 1,
  source_version: 0,
  context_snapshot: "a".repeat(64),
  preview_snapshot: id.repeat(64).slice(0, 64),
  amount_minor: 10000,
  currency: "PLN",
  before_parts: [{ category_id: "marker", amount_minor: 10000 }],
  after_parts: [{ category_id: "target", amount_minor: 10000 }],
  target_path: "Dom / Czynsz",
  explanation: "Opis pasuje do domu",
  confidence: "high",
  expires_at: "2026-11-11T12:00:00Z",
});

beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 42 });
});
function mount(items = [item("a"), item("b")]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProposalReview items={items} maxItems={20} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}
async function reviewBoth() {
  fireEvent.click(screen.getByLabelText("Wybierz Wydatek a"));
  fireEvent.click(screen.getByLabelText("Wybierz Wydatek b"));
  fireEvent.click(
    screen.getByRole("button", { name: "Przejrzyj wybrane (2)" }),
  );
  await screen.findByRole("button", { name: "Zatwierdź wybrane (2)" });
}

it("requires review, posts exactly selected previews and reports a partial conflict", async () => {
  const sent: string[] = [];
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  vi.spyOn(api, "post").mockImplementation(async (url, body) => {
    const id = String(url).split("/").slice(-2)[0];
    if (String(url).endsWith("/preview")) return { data: preview(id) };
    sent.push(id);
    expect(body).toEqual({
      expected_version: 1,
      preview_snapshot: id.repeat(64),
      confirmed: true,
    });
    if (id === "b")
      throw {
        response: { status: 409, data: { detail: "Dane zmieniły się" } },
      };
    return { data: { proposal_id: id, version: 2, status: "approved" } };
  });
  mount();
  expect(
    screen.queryByRole("button", { name: /Zatwierdź wybrane/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Wybierz Wydatek a")).not.toBeChecked();
  await reviewBoth();
  expect(sent).toEqual([]);
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź wybrane (2)" }),
  );
  await screen.findByText("Dane zmieniły się — sprawdź ponownie");
  expect(sent).toEqual(["a", "b"]);
  expect(screen.getByText("Zatwierdzono")).toBeInTheDocument();
});

it("unknown stops the sequence and retry reuses frozen keys through a queue refetch", async () => {
  const sent: { id: string; key: string; body: unknown }[] = [];
  let fail = true;
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  vi.spyOn(api, "post").mockImplementation(async (url, body, options) => {
    const id = String(url).split("/").slice(-2)[0];
    if (String(url).endsWith("/preview")) return { data: preview(id) };
    sent.push({
      id,
      key: options?.headers?.["Idempotency-Key"] as string,
      body,
    });
    if (fail) {
      fail = false;
      throw new Error("Disconnected");
    }
    return { data: { proposal_id: id, version: 2, status: "approved" } };
  });
  const view = mount();
  await reviewBoth();
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź wybrane (2)" }),
  );
  await screen.findByRole("button", { name: "Ponów niedokończone" });
  expect(sent.map((x) => x.id)).toEqual(["a"]);
  view.rerender(
    <QueryClientProvider client={view.client}>
      <MemoryRouter>
        <ProposalReview items={[]} maxItems={20} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByText("Wydatek a")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ponów niedokończone" }));
  await waitFor(() => expect(sent).toHaveLength(3));
  expect(sent[0]).toEqual(sent[1]);
  expect(sent.map((x) => x.id)).toEqual(["a", "a", "b"]);
});

it("session replacement stops unseen items and ignores late success", async () => {
  let resolve!: (value: { data: unknown }) => void;
  const sent: string[] = [];
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  vi.spyOn(api, "post").mockImplementation(async (url) => {
    const id = String(url).split("/").slice(-2)[0];
    if (String(url).endsWith("/preview")) return { data: preview(id) };
    sent.push(id);
    return new Promise((r) => {
      resolve = r;
    });
  });
  mount();
  await reviewBoth();
  fireEvent.click(
    screen.getByRole("button", { name: "Zatwierdź wybrane (2)" }),
  );
  await waitFor(() => expect(sent).toEqual(["a"]));
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
    resolve({ data: { proposal_id: "a", version: 2, status: "approved" } });
  });
  expect(sent).toEqual(["a"]);
  expect(screen.getByText(/Sesja zmieniła się/)).toBeInTheDocument();
  expect(screen.queryByText("Zatwierdzono")).not.toBeInTheDocument();
});

it("new category cannot be selected or batch-applied and keeps the separate manual path", () => {
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  const proposed = {
    ...item("n"),
    eligible: false,
    decision: "new_category",
    new_category: {
      name: "Proponowana",
      parent_path: "Dom",
      explanation: "Nowa grupa",
    },
    blocked_reason: "manual_category_required",
  };
  mount([proposed]);
  expect(screen.queryByLabelText("Wybierz Wydatek n")).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Utwórz kategorię osobno" }),
  ).toHaveAttribute("href", "/settings/finances/categories");
  expect(
    screen.getByRole("button", { name: "Przypisz ręcznie" }),
  ).toBeInTheDocument();
});

it("a refetch during the first apply cannot replace the second reviewed item or double-launch", async () => {
  let resolve!: (value: { data: unknown }) => void;
  const sent: { id: string; body: unknown }[] = [];
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  vi.spyOn(api, "post").mockImplementation(async (url, body) => {
    const id = String(url).split("/").slice(-2)[0];
    if (String(url).endsWith("/preview")) return { data: preview(id) };
    sent.push({ id, body });
    return id === "a"
      ? new Promise((r) => {
          resolve = r;
        })
      : { data: { proposal_id: id, version: 2, status: "approved" } };
  });
  const view = mount();
  await reviewBoth();
  const confirm = screen.getByRole("button", { name: "Zatwierdź wybrane (2)" });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  await waitFor(() => expect(sent).toHaveLength(1));
  view.rerender(
    <QueryClientProvider client={view.client}>
      <MemoryRouter>
        <ProposalReview
          items={[
            { ...item("b"), version: 99, target_path: "Unseen category" },
          ]}
          maxItems={20}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await act(async () => {
    useAuthStore.setState({ authStatus: "authenticated" });
    resolve({ data: { proposal_id: "a", version: 2, status: "approved" } });
  });
  await waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[1]).toEqual({
    id: "b",
    body: {
      expected_version: 1,
      preview_snapshot: "b".repeat(64),
      confirmed: true,
    },
  });
  expect(screen.queryByText("Unseen category")).not.toBeInTheDocument();
});

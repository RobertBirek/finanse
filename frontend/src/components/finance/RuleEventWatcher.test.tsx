import { act, cleanup, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { FinanceTabs } from "./FinanceTabs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
it("refreshes ledger after the event read even if the worker already finished, never invalidating itself", async () => {
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "u@example.com",
      display_name: "U",
      is_active: true,
    },
    authStatus: "authenticated",
  });
  vi.spyOn(api, "get").mockResolvedValue({
    data: { events: [], poll_after_ms: 2000 },
  });
  const client = new QueryClient();
  const invalidation = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FinanceTabs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(api.get).toHaveBeenCalledWith(
      "/finance/categorization/events",
      expect.anything(),
    ),
  );
  await waitFor(() =>
    expect(invalidation).toHaveBeenCalledWith({
      queryKey: ["finance", "transactions"],
    }),
  );
  expect(invalidation).not.toHaveBeenCalledWith({
    queryKey: ["finance", "rule-events"],
  });
  client.clear();
});
it("ignores a late event response from the previous session", async () => {
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "u@example.com",
      display_name: "U",
      is_active: true,
    },
    authStatus: "authenticated",
  });
  let finish!: (value: unknown) => void;
  vi.spyOn(api, "get").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const client = new QueryClient();
  const invalidation = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FinanceTabs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  act(() =>
    useAuthStore.setState((s) => ({
      user: null,
      sessionVersion: s.sessionVersion + 1,
    })),
  );
  await act(async () => {
    finish({ data: { events: [], poll_after_ms: 2000 } });
  });
  expect(invalidation).not.toHaveBeenCalled();
  client.clear();
});

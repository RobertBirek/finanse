import { act, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { SuggestionActivityWatcher } from "./SuggestionActivityWatcher";
beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 42 });
});
it("a fast completed first read refreshes proposals and usage, never itself", async () => {
  vi.spyOn(api, "get").mockResolvedValue({
    data: { active_jobs: [], recent_outcomes: [], poll_after_ms: 20 },
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <SuggestionActivityWatcher />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["finance", "proposals"],
    }),
  );
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["finance", "suggestions"],
  });
  expect(invalidate).not.toHaveBeenCalledWith({
    queryKey: ["finance", "suggestion-activity"],
  });
});
it("old-session completion cannot refresh a new user's state", async () => {
  let resolve!: (v: { data: unknown }) => void;
  vi.spyOn(api, "get").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <SuggestionActivityWatcher />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  const old = resolve;
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
    old({ data: { active_jobs: [], recent_outcomes: [], poll_after_ms: 20 } });
  });
  expect(invalidate).not.toHaveBeenCalled();
});

it("polls only active jobs and stops after the terminal response", async () => {
  const get = vi
    .spyOn(api, "get")
    .mockResolvedValueOnce({
      data: {
        active_jobs: [{ id: "j", state: "ready" }],
        recent_outcomes: [],
        poll_after_ms: 20,
      },
    })
    .mockResolvedValue({
      data: {
        active_jobs: [],
        recent_outcomes: [{ id: "j", state: "completed" }],
        poll_after_ms: 20,
      },
    });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <SuggestionActivityWatcher />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 80));
  });
  expect(get).toHaveBeenCalledTimes(2);
  view.unmount();
  client.clear();
});

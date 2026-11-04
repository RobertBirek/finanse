import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, it, expect, vi } from "vitest";
import { useApplyProposal, usePreviewProposal } from "./categoryProposals";
import { useCreateTransaction } from "./finance";
import { useAuthStore } from "../stores/authStore";
import api from "../lib/api";
beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 42 });
});
function wrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return {
    client,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}
it("late receipt is not installed as current state and previous-session writes are fenced", async () => {
  const { client, Wrapper } = wrapper();
  const key = ["finance", "proposals", 42, "pending", null];
  const current = { items: [{ id: "still-current" }] };
  client.setQueryData(key, current);
  let resolve!: (v: { data: unknown }) => void;
  const post = vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const { result } = renderHook(() => useApplyProposal(), { wrapper: Wrapper });
  let pending!: Promise<unknown>;
  await act(async () => {
    pending = result.current.mutateAsync({
      session: 42,
      id: "p",
      key: "same-key",
      expected_version: 1,
      preview_snapshot: "a".repeat(64),
      confirmed: true,
    });
  });
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
    resolve({
      data: {
        proposal_id: "p",
        version: 2,
        status: "approved",
        context: { old: "receipt" },
      },
    });
    await pending;
  });
  expect(client.getQueryData(key)).toEqual(current);
  expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  await act(async () => {
    await expect(
      result.current.mutateAsync({
        session: 42,
        id: "other",
        key: "old",
        expected_version: 1,
        preview_snapshot: "a".repeat(64),
        confirmed: true,
      }),
    ).rejects.toThrow("session_changed");
  });
  expect(post).toHaveBeenCalledTimes(1);
  client.clear();
});
it("preview never posts session or authority fields", async () => {
  const { client, Wrapper } = wrapper();
  const post = vi
    .spyOn(api, "post")
    .mockResolvedValue({ data: { preview_snapshot: "a".repeat(64) } });
  const { result } = renderHook(() => usePreviewProposal(), {
    wrapper: Wrapper,
  });
  await act(async () => {
    await result.current.mutateAsync({ session: 42, id: "p", version: 1 });
  });
  expect(post.mock.calls[0][1]).toEqual({ expected_version: 1 });
  client.clear();
});
it("new expense wakes the suggestion watcher, not a historical generation endpoint", async () => {
  const { client, Wrapper } = wrapper();
  vi.spyOn(api, "post").mockResolvedValue({ data: { id: "new" } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const { result } = renderHook(() => useCreateTransaction(), {
    wrapper: Wrapper,
  });
  await act(async () => {
    await result.current.mutateAsync({
      type: "expense",
      description: "New",
      postings: [],
    });
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["finance", "suggestion-activity"],
  });
  client.clear();
});

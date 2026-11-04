import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { useApplyCategorization } from "./categorization";

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
it("replayed approval only invalidates current reads, not installs its historical snapshot", async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const install = vi.spyOn(client, "setQueryData");
  vi.spyOn(api, "post").mockResolvedValue({ data: { version: 1 } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useApplyCategorization(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({
      id: "txn",
      key: "same-key",
      expected_version: 0,
      expected_preview_snapshot: "a".repeat(64),
      parts: [{ category_id: "food", amount_minor: 10000 }],
      confirmed: true,
    });
  });
  expect(invalidate).toHaveBeenCalled();
  expect(install).not.toHaveBeenCalled();
  client.clear();
});
it("late approval after logout and same-owner login cannot invalidate the new session", async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  let finish!: (value: unknown) => void;
  vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useApplyCategorization(), { wrapper });
  let pending!: Promise<unknown>;
  await act(async () => {
    pending = result.current.mutateAsync({
      id: "txn",
      key: "same-key",
      expected_version: 0,
      expected_preview_snapshot: "a".repeat(64),
      parts: [{ category_id: "food", amount_minor: 10000 }],
      confirmed: true,
    });
  });
  act(() =>
    useAuthStore.setState((state) => ({
      sessionVersion: state.sessionVersion + 2,
    })),
  );
  await act(async () => {
    finish({ data: { version: 1 } });
    await pending;
  });
  expect(invalidate).not.toHaveBeenCalled();
  client.clear();
});

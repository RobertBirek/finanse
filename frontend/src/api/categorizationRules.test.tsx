import type { ReactNode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useCreateTransaction } from "./finance";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("asks the event watcher to refresh after creating a new expense", async () => {
  vi.spyOn(api, "post").mockResolvedValue({ data: { id: "new" } });
  const client = new QueryClient();
  const invalidation = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useCreateTransaction(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({
      description: "Czynsz",
      type: "expense",
      postings: [],
    });
  });
  expect(invalidation).toHaveBeenCalledWith({
    queryKey: ["finance", "rule-events"],
  });
  client.clear();
});

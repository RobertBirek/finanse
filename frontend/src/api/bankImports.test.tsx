import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it } from "vitest";
import { useImport, useCommitImport } from "./bankImports";
import {
  importTestWrapper,
  installImportServer,
  receiptFixture,
  setImportActor,
} from "../test/bankImportFixtures";
import type { ReactNode } from "react";

let server: ReturnType<typeof installImportServer>;
afterEach(() => server?.restore());
function wrapper({ children }: { children: ReactNode }) {
  return importTestWrapper(children).node;
}

it("fences a late mutation after the owner changes and does not invalidate the new owner's ledger", async () => {
  let finish!: (value: unknown) => void;
  server = installImportServer({
    onRequest: (request) =>
      request.url.endsWith("/commit")
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : undefined,
  });
  const { result } = renderHook(() => useCommitImport(), { wrapper });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current
      .mutateAsync({
        batchId: "batch-a",
        data: { preview_id: "preview-a", request_hash: "b".repeat(64) },
        idempotencyKey: "one-intent",
      })
      .catch((error) => error);
  });
  await waitFor(() => expect(finish).toBeDefined());
  act(() => setImportActor("owner-b"));
  await act(async () => {
    finish(receiptFixture);
    await pending;
  });
  expect(result.current.data).toBeUndefined();
});

it("uses owner and generation scoped import query keys", async () => {
  server = installImportServer();
  const context = importTestWrapper(null);
  const hook = renderHook(() => useImport("batch-a"), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={context.client}>
        {children}
      </QueryClientProvider>
    ),
  });
  await waitFor(() => expect(hook.result.current.data?.id).toBe("batch-a"));
  const keys = context.client
    .getQueryCache()
    .getAll()
    .map((query) => query.queryKey);
  expect(
    keys.some(
      (key) =>
        key[0] === "finance" &&
        key[1] === "imports" &&
        key[2] === "owner-a" &&
        typeof key[3] === "number",
    ),
  ).toBe(true);
});

it("does not accept a receipt bound to a different import request", async () => {
  server = installImportServer({
    onRequest: (request) =>
      request.url.endsWith("/commit") || request.url.includes("/commands/")
        ? { ...receiptFixture, batch_id: "another-batch" }
        : undefined,
  });
  const { result } = renderHook(() => useCommitImport(), { wrapper });
  let outcome: unknown;
  await act(async () => {
    try {
      outcome = await result.current.mutateAsync({
        batchId: "batch-a",
        data: { preview_id: "preview-a", request_hash: "b".repeat(64) },
        idempotencyKey: "bound-intent",
      });
    } catch (error) {
      outcome = error;
    }
  });
  expect(outcome).toBeInstanceOf(Error);
  expect(result.current.data).toBeUndefined();
});

import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it } from "vitest";
import type { ReactNode } from "react";
import {
  useActivateSchedule,
  useLoanScheduleRevisions,
} from "./loanScheduleImports";
import {
  httpFailure,
  importTestWrapper,
  setImportActor,
} from "../test/bankImportFixtures";
import {
  installScheduleServer,
  scheduleReceipt,
  schedulePreview,
} from "../test/loanScheduleFixtures";

let server: ReturnType<typeof installScheduleServer>;
afterEach(() => server?.restore());
function wrapper({ children }: { children: ReactNode }) {
  return importTestWrapper(children).node;
}
const input = {
  batchId: "batch-a",
  data: {
    preview_id: schedulePreview.id,
    request_hash: schedulePreview.request_hash,
  },
  idempotencyKey: "one-schedule-intent",
};

it("recovers a lost activation response with the same durable key and no ledger mutation", async () => {
  server = installScheduleServer({
    onRequest: (r) => {
      if (r.url.endsWith("/activate-schedule"))
        throw httpFailure(503, {}, r.config);
    },
  });
  const { result } = renderHook(() => useActivateSchedule(), { wrapper });
  await act(async () => {
    expect(await result.current.mutateAsync(input)).toEqual(scheduleReceipt);
  });
  expect(
    server.requests.filter((r) => r.method === "post").map((r) => r.key),
  ).toEqual(["one-schedule-intent"]);
  expect(
    server.requests.some((r) =>
      r.url.endsWith("/commands/one-schedule-intent"),
    ),
  ).toBe(true);
});

it("does not publish late activation data after actor generation changes", async () => {
  let finish!: (value: unknown) => void;
  server = installScheduleServer({
    onRequest: (r) =>
      r.url.endsWith("/activate-schedule")
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : undefined,
  });
  const { result } = renderHook(() => useActivateSchedule(), { wrapper });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.mutateAsync(input).catch((e) => e);
  });
  await waitFor(() => expect(finish).toBeDefined());
  act(() => setImportActor("owner-b"));
  await act(async () => {
    finish(scheduleReceipt);
    await pending;
  });
  expect(result.current.data).toBeUndefined();
  expect(server.requests.some((r) => r.url.includes("/commands/"))).toBe(false);
});

it("rejects a receipt for a different schedule hash and any ledger_changed true result", async () => {
  server = installScheduleServer({
    onRequest: (r) =>
      r.url.endsWith("/activate-schedule") || r.url.includes("/commands/")
        ? { ...scheduleReceipt, ledger_changed: true, request_hash: "wrong" }
        : undefined,
  });
  const { result } = renderHook(() => useActivateSchedule(), { wrapper });
  let outcome: unknown;
  await act(async () => {
    outcome = await result.current.mutateAsync(input).catch((e) => e);
  });
  expect(outcome).toBeInstanceOf(Error);
  expect(result.current.data).toBeUndefined();
});

it("scopes history reads to owner and generation", async () => {
  server = installScheduleServer();
  const context = importTestWrapper(null);
  const hook = renderHook(() => useLoanScheduleRevisions("loan-a"), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={context.client}>
        {children}
      </QueryClientProvider>
    ),
  });
  await waitFor(() => expect(hook.result.current.data?.length).toBe(2));
  expect(
    context.client
      .getQueryCache()
      .getAll()
      .some(
        (q) =>
          q.queryKey.includes("owner-a") &&
          q.queryKey.some((value) => typeof value === "number"),
      ),
  ).toBe(true);
});

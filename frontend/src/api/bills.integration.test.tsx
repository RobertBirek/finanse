import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  useAllocateBillPayment,
  useApproveBill,
  useAttachBillSource,
  useBill,
  useSerializedIntentKey,
  useUnlinkBillPayment,
  useUpdateBillLifecycle,
} from "./bills";
import { useCashflowForecast } from "./finance";
import api from "../lib/api";

afterEach(() => vi.restoreAllMocks());

function withClient(ui: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      {ui}
    </QueryClientProvider>,
  );
}

function AllocationProbe() {
  const bill = useBill("bill-1");
  const forecast = useCashflowForecast();
  const allocate = useAllocateBillPayment();
  if (!bill.data || !forecast.data) return <p>loading</p>;
  return (
    <>
      <p>paid {bill.data.paid_minor}</p>
      <p>remaining {bill.data.remaining_minor}</p>
      <p>forecast {forecast.data.suggestions[0]?.amount_pln}</p>
      <button
        type="button"
        onClick={() =>
          allocate.mutate({
            billId: bill.data.id,
            version: bill.data.version,
            posting_id: "posting-1",
            amount_minor: 4000,
            idempotencyKey: "allocate-40",
          })
        }
      >
        allocate 40
      </button>
    </>
  );
}

function IntentProbe() {
  const [version, setVersion] = useState(4);
  const keyFor = useSerializedIntentKey();
  const lifecycle = useUpdateBillLifecycle();
  const unlink = useUnlinkBillPayment();
  return (
    <>
      <button
        type="button"
        onClick={() =>
          lifecycle.mutate({
            billId: "bill-1",
            expected_version: version,
            lifecycle: "archived",
            confirm_forecast_effect: true,
            idempotencyKey: keyFor({ action: "lifecycle", version }),
          })
        }
      >
        lifecycle
      </button>
      <button
        type="button"
        onClick={() =>
          unlink.mutate({
            billId: "bill-1",
            allocationId: "allocation-1",
            expected_version: version,
            idempotencyKey: keyFor({ action: "unlink", version }),
          })
        }
      >
        unlink
      </button>
      <button type="button" onClick={() => setVersion(5)}>
        next version
      </button>
    </>
  );
}

function ApprovalIntentProbe() {
  const [supplier, setSupplier] = useState("A");
  const [reordered, setReordered] = useState(false);
  const approve = useApproveBill();
  const keyFor = useSerializedIntentKey();
  const data = reordered
    ? {
        currency: "PLN" as const,
        total_minor: 100,
        description: "B",
        category_id: "category-1",
        supplier_name: supplier,
        kind: "invoice" as const,
        version: 1,
      }
    : {
        version: 1,
        kind: "invoice" as const,
        supplier_name: supplier,
        description: "B",
        total_minor: 100,
        currency: "PLN" as const,
        category_id: "category-1",
      };
  return (
    <>
      <button
        type="button"
        onClick={() =>
          approve.mutate({
            billId: "draft",
            data,
            idempotencyKey: keyFor({
              action: "approve",
              billId: "draft",
              data,
            }),
          })
        }
      >
        approve
      </button>
      <button type="button" onClick={() => setSupplier("Changed")}>
        change supplier
      </button>
      <button type="button" onClick={() => setReordered(true)}>
        reorder fields
      </button>
    </>
  );
}

describe("bill API integration", () => {
  it("refetches bill and cashflow state after allocating 40 of 100", async () => {
    const state = { paid_minor: 0, remaining_minor: 10000, forecast: 100 };
    const get = vi.spyOn(api, "get").mockImplementation((url) => {
      if (url === "/finance/bills/bill-1")
        return Promise.resolve({
          data: { id: "bill-1", version: 1, ...state },
        } as never);
      if (url === "/finance/cashflow/forecast")
        return Promise.resolve({
          data: { suggestions: [{ amount_pln: state.forecast }] },
        } as never);
      return Promise.resolve({ data: [] } as never);
    });
    const post = vi.spyOn(api, "post").mockImplementation((url) => {
      if (url === "/finance/bills/bill-1/allocations") {
        state.paid_minor = 4000;
        state.remaining_minor = 6000;
        state.forecast = 60;
      }
      return Promise.resolve({
        data: { id: "bill-1", version: 2, ...state },
      } as never);
    });

    withClient(<AllocationProbe />);
    await screen.findByText("remaining 10000");
    fireEvent.click(screen.getByRole("button", { name: "allocate 40" }));

    await screen.findByText("paid 4000");
    expect(screen.getByText("remaining 6000")).toBeInTheDocument();
    expect(screen.getByText("forecast 60")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith(
      "/finance/bills/bill-1/allocations",
      expect.objectContaining({ amount_minor: 4000 }),
      expect.anything(),
    );
    expect(
      get.mock.calls.filter(([url]) => url === "/finance/bills/bill-1").length,
    ).toBeGreaterThan(1);
    expect(
      get.mock.calls.filter(([url]) => url === "/finance/cashflow/forecast")
        .length,
    ).toBeGreaterThan(1);
  });

  it("reuses lifecycle and unlink keys for a retry, but changes them for a new version", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} } as never);
    const remove = vi
      .spyOn(api, "delete")
      .mockResolvedValue({ data: {} } as never);
    withClient(<IntentProbe />);

    fireEvent.click(screen.getByRole("button", { name: "lifecycle" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "lifecycle" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "unlink" }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "unlink" }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "next version" }));
    fireEvent.click(screen.getByRole("button", { name: "lifecycle" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole("button", { name: "unlink" }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(3));

    const postHeader = (call: unknown[]) =>
      (call[2] as { headers: { "Idempotency-Key": string } }).headers[
        "Idempotency-Key"
      ];
    const deleteHeader = (call: unknown[]) =>
      (call[1] as { headers: { "Idempotency-Key": string } }).headers[
        "Idempotency-Key"
      ];
    expect(postHeader(post.mock.calls[0])).toBe(postHeader(post.mock.calls[1]));
    expect(postHeader(post.mock.calls[2])).not.toBe(
      postHeader(post.mock.calls[1]),
    );
    expect(deleteHeader(remove.mock.calls[0])).toBe(
      deleteHeader(remove.mock.calls[1]),
    );
    expect(deleteHeader(remove.mock.calls[2])).not.toBe(
      deleteHeader(remove.mock.calls[1]),
    );
    expect(post.mock.calls[2][1]).toMatchObject({
      expected_version: 5,
      confirm_forecast_effect: true,
    });
    expect(
      (remove.mock.calls[2][1] as { params: unknown }).params,
    ).toMatchObject({ expected_version: 5 });
  });

  it("sends caller-owned keys for approval and source attachment", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} } as never);
    function ReviewMutations() {
      const approve = useApproveBill();
      const attach = useAttachBillSource();
      return (
        <button
          type="button"
          onClick={() => {
            approve.mutate({
              billId: "draft",
              data: {
                version: 1,
                kind: "invoice",
                supplier_name: "A",
                description: "B",
                total_minor: 100,
                currency: "PLN",
              },
              idempotencyKey: "approve-intent",
            });
            attach.mutate({
              billId: "target",
              documentId: "source",
              expectedVersion: 2,
              idempotencyKey: "attach-intent",
            });
          }}
        >
          mutate review
        </button>
      );
    }
    withClient(<ReviewMutations />);
    fireEvent.click(screen.getByRole("button", { name: "mutate review" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(
      (post.mock.calls[0][2] as { headers: { "Idempotency-Key": string } })
        .headers["Idempotency-Key"],
    ).toBe("approve-intent");
    expect(
      (post.mock.calls[1][2] as { headers: { "Idempotency-Key": string } })
        .headers["Idempotency-Key"],
    ).toBe("attach-intent");
  });

  it("keeps a nested approval retry key, changes nested data keys, and ignores deep object ordering", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} } as never);
    withClient(<ApprovalIntentProbe />);
    fireEvent.click(screen.getByRole("button", { name: "approve" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "approve" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "reorder fields" }));
    fireEvent.click(screen.getByRole("button", { name: "approve" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole("button", { name: "change supplier" }));
    fireEvent.click(screen.getByRole("button", { name: "approve" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(4));

    const key = (call: unknown[]) =>
      (call[2] as { headers: { "Idempotency-Key": string } }).headers[
        "Idempotency-Key"
      ];
    expect(key(post.mock.calls[0])).toBe(key(post.mock.calls[1]));
    expect(key(post.mock.calls[2])).toBe(key(post.mock.calls[1]));
    expect(key(post.mock.calls[3])).not.toBe(key(post.mock.calls[2]));
  });
});

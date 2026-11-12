import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { useAuthStore } from "../../../stores/authStore";
import { syntheticBill } from "../../../test/billFixtures";
import { BillDeclarationDialog } from "./BillDeclarationDialog";

afterEach(() => vi.restoreAllMocks());

function setup(declaration: "declared_paid" | "payable" = "declared_paid") {
  const bill = syntheticBill(
    declaration === "payable"
      ? {
          declaration: "declared_paid",
          paid_minor: 4000,
          remaining_minor: 6000,
          reconciliation: "partial",
        }
      : {},
  );
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const onClose = vi.fn();
  const ui = (value = bill) => (
    <QueryClientProvider client={client}>
      <BillDeclarationDialog
        bill={value}
        declaration={declaration}
        onClose={onClose}
      />
    </QueryClientProvider>
  );
  return { ...render(ui()), client, onClose, bill, ui };
}

const confirm = () => {
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź oznaczenie" }));
};

describe("BillDeclarationDialog", () => {
  it("sends only the confirmed declaration and invalidates obligations, not ledger caches", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: syntheticBill({
        declaration: "declared_paid",
        version: 3,
      }),
    });
    const { client, onClose } = setup();
    for (const key of [
      ["finance", "bills"],
      ["finance", "cashflow"],
      ["documents"],
      ["finance", "transactions"],
      ["finance", "summary"],
    ])
      client.setQueryData(key, {});
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
    ).toBeDisabled();
    confirm();
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledExactlyOnceWith(
      "/finance/bills/bill-1/payment-declaration",
      {
        expected_version: 2,
        declaration: "declared_paid",
        confirm_forecast_effect: true,
      },
      { headers: { "Idempotency-Key": expect.any(String) } },
    );
    expect(client.getQueryState(["finance", "bills"])?.isInvalidated).toBe(
      true,
    );
    expect(client.getQueryState(["finance", "cashflow"])?.isInvalidated).toBe(
      true,
    );
    expect(client.getQueryState(["documents"])?.isInvalidated).toBe(true);
    expect(
      client.getQueryState(["finance", "transactions"])?.isInvalidated,
    ).toBe(false);
    expect(client.getQueryState(["finance", "summary"])?.isInvalidated).toBe(
      false,
    );
  });

  it("retry reuses the declaration intent after a transport failure", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ data: syntheticBill() });
    const { onClose } = setup();
    confirm();
    await screen.findByRole("alert");
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(post.mock.calls[0]).toEqual(post.mock.calls[1]);
  });

  it("conflict requires refresh and a new decision against the current amount", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ data: syntheticBill() });
    const get = vi.spyOn(api, "get").mockResolvedValue({
      data: syntheticBill({
        version: 3,
        paid_minor: 4000,
        remaining_minor: 6000,
        reconciliation: "partial",
      }),
    });
    setup();
    confirm();
    await screen.findByRole("button", { name: "Odśwież dokument" });
    expect(
      screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Odśwież dokument" }));
    await screen.findByText(/60,00\s*zł/);
    expect(get).toHaveBeenCalledWith("/finance/bills/bill-1");
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
    ).toBeDisabled();
    confirm();
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toEqual({
      expected_version: 3,
      declaration: "declared_paid",
      confirm_forecast_effect: true,
    });
    expect(post.mock.calls[1][2]?.headers?.["Idempotency-Key"]).not.toBe(
      post.mock.calls[0][2]?.headers?.["Idempotency-Key"],
    );
  });

  it("blocks a second submission while a request is in flight", async () => {
    let resolve!: (value: never) => void;
    const post = vi.spyOn(api, "post").mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    setup();
    confirm();
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    const submit = screen.getByRole("button", { name: "Potwierdź oznaczenie" });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(post).toHaveBeenCalledOnce();
    await act(async () => resolve({ data: syntheticBill() } as never));
  });

  it("starts a new intent after a conflict even when the refreshed version is unchanged", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ data: syntheticBill() });
    vi.spyOn(api, "get").mockResolvedValue({ data: syntheticBill() });
    setup();
    confirm();
    fireEvent.click(
      await screen.findByRole("button", { name: "Odśwież dokument" }),
    );
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    confirm();
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1][1]).toEqual(post.mock.calls[0][1]);
    expect(post.mock.calls[1][2]?.headers?.["Idempotency-Key"]).not.toBe(
      post.mock.calls[0][2]?.headers?.["Idempotency-Key"],
    );
  });

  it("undo restores only the remainder without reversing bank payments", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue({ data: syntheticBill() });
    setup("payable");
    expect(screen.getByText(/60,00\s*zł/)).toBeInTheDocument();
    expect(screen.getByText(/nie cofa.*przelew/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", { name: "Przywróć do zapłaty" }),
    );
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(post.mock.calls[0][1]).toEqual({
      expected_version: 2,
      declaration: "payable",
      confirm_forecast_effect: true,
    });
  });

  it.each(["document", "session"])(
    "never reuses consent after a %s change",
    async (change) => {
      const post = vi
        .spyOn(api, "post")
        .mockResolvedValue({ data: syntheticBill() });
      const view = setup();
      fireEvent.click(screen.getByRole("checkbox"));
      if (change === "document")
        view.rerender(view.ui(syntheticBill({ id: "bill-2" })));
      else
        act(() =>
          useAuthStore.setState((state) => ({
            sessionVersion: state.sessionVersion + 1,
          })),
        );
      expect(
        screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
      ).toBeDisabled();
      fireEvent.click(
        screen.getByRole("button", { name: "Potwierdź oznaczenie" }),
      );
      expect(post).not.toHaveBeenCalled();
    },
  );
});

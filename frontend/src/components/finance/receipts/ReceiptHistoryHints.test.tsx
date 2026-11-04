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
import api from "../../../lib/api";
import { ReceiptHistoryHints } from "./ReceiptHistoryHints";
import { hint } from "./receiptTestData";
import { useAuthStore } from "../../../stores/authStore";
beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 42 });
});
it("a late hint after editing the name is ignored, not installed as a category", async () => {
  let resolve!: (v: { data: unknown }) => void;
  vi.spyOn(api, "get").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const choose = vi.fn(),
    client = new QueryClient();
  const element = (name: string) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReceiptHistoryHints
          billId="bill"
          storeId="store"
          name={name}
          categoryId={null}
          disabled={false}
          onChoose={choose}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(element("Mleko"));
  fireEvent.click(
    screen.getByRole("button", { name: "Sprawdź historię sklepu" }),
  );
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  view.rerender(element("Inny produkt"));
  await act(async () => {
    resolve({
      data: {
        items: [hint],
        match_kind: "exact",
        conflict: false,
        has_more: false,
        history_incomplete: false,
      },
    });
  });
  expect(
    screen.queryByRole("button", { name: "Użyj kategorii" }),
  ).not.toBeInTheDocument();
  expect(choose).not.toHaveBeenCalled();
});
it("history is requested explicitly and adopting it never sends a financial write", async () => {
  const get = vi
    .spyOn(api, "get")
    .mockResolvedValue({
      data: {
        items: [hint],
        match_kind: "exact",
        conflict: true,
        has_more: true,
        history_incomplete: true,
      },
    });
  const post = vi.spyOn(api, "post");
  const choose = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ReceiptHistoryHints
          billId="bill"
          storeId="store"
          name="Mleko"
          categoryId={null}
          disabled={false}
          onChoose={choose}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(get).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Sprawdź historię sklepu" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Użyj kategorii" }),
  );
  expect(choose).toHaveBeenCalledWith(hint.ref);
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByText(/Historia jest niepełna/)).toBeInTheDocument();
});

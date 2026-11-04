import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { ReceiptLineEditor } from "./ReceiptLineEditor";
import { fromReceiptBody, toReceiptBody } from "./receiptDraft";
import { body, categories, hint } from "./receiptTestData";
it("editing the name or category clears adopted history without changing the price", () => {
  const change = vi.fn();
  const line = { ...fromReceiptBody(body).lines[0], hint: hint.ref };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ReceiptLineEditor
          line={line}
          index={0}
          billId="bill"
          storeId="store"
          categories={categories}
          excludedIds={new Set()}
          disabled={false}
          maxName={300}
          onChange={change}
          onDelete={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("Produkt 1"), {
    target: { value: "Inna nazwa" },
  });
  expect(change).toHaveBeenLastCalledWith({
    ...line,
    name: "Inna nazwa",
    hint: null,
  });
  fireEvent.change(screen.getByLabelText("Kategoria produktu 1"), {
    target: { value: "home" },
  });
  expect(change).toHaveBeenLastCalledWith({
    ...line,
    category_id: "home",
    hint: null,
  });
});
it.each(["12.345", "-1", "abc", "90071992547409.92"])(
  "rejects invalid nonblank input %s without turning it into a missing amount",
  (raw) => {
    const draft = fromReceiptBody(body);
    draft.lines[0].amount = raw;
    expect(() => toReceiptBody(draft)).toThrow();
  },
);
it("zero and absent amounts stay distinct integers and explicit shares stay exact", () => {
  const draft = fromReceiptBody(body);
  draft.lines[0].amount = "0";
  draft.lines[1].amount = "";
  const result = toReceiptBody(draft);
  expect(result.lines.map((l) => l.amount_minor)).toEqual([0, null]);
  expect(result.discounts[0].shares).toEqual([
    { line_key: "a", amount_minor: 800 },
    { line_key: "b", amount_minor: 200 },
  ]);
});

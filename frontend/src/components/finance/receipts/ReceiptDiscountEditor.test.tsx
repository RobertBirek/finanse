import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ReceiptDiscountEditor } from "./ReceiptDiscountEditor";
import { fromReceiptBody } from "./receiptDraft";
import { body } from "./receiptTestData";
it("does not redistribute a changed discount or alter other explicit shares", () => {
  const draft = fromReceiptBody(body),
    discount = draft.discounts[0],
    change = vi.fn();
  render(
    <ReceiptDiscountEditor
      discount={discount}
      index={0}
      lines={draft.lines}
      disabled={false}
      maxName={300}
      onChange={change}
      onDelete={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText("Kwota rabatu 1"), {
    target: { value: "11,00" },
  });
  expect(change).toHaveBeenLastCalledWith({ ...discount, amount: "11,00" });
  fireEvent.change(screen.getByLabelText("Udział rabatu 1, produkt 1"), {
    target: { value: "9,00" },
  });
  expect(change).toHaveBeenLastCalledWith({
    ...discount,
    shares: { a: "9,00", b: "2,00" },
  });
});

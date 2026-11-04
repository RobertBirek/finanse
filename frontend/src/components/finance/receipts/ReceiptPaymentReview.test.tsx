import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ReceiptPaymentReview } from "./ReceiptPaymentReview";
import { preview, categories } from "./receiptTestData";
it("requires a separate explicit confirmation while showing both categories and preserved payment amount", () => {
  const confirm = vi.fn();
  render(
    <ReceiptPaymentReview
      preview={preview}
      categories={categories}
      disabled={false}
      onConfirm={confirm}
      onCancel={() => {}}
    />,
  );
  expect(screen.getByText("Sprawdź podział 90,00 zł")).toBeInTheDocument();
  expect(screen.getByText("Spożywka: 72,00 zł")).toBeInTheDocument();
  expect(screen.getByText("Dom: 18,00 zł")).toBeInTheDocument();
  expect(confirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź podział" }));
  expect(confirm).toHaveBeenCalledOnce();
});

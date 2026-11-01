import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DocumentReview } from "../../api/documents";
import { useReviewForm } from "./useReviewForm";

const review = (
  revision: number,
  fields: Partial<DocumentReview["fields"]> = {
    total: "12.34",
    currency: "PLN",
  },
): DocumentReview => ({
  id: `revision-${revision}`,
  document_id: "doc-1",
  revision,
  status: "ready" as const,
  document_type: "invoice" as const,
  error_code: null,
  fields: {
    supplier_name: "Sklep",
    supplier_tax_id: null,
    number: null,
    issue_date: null,
    sale_date: null,
    due_date: null,
    description: "Zakupy",
    payee_iban: null,
    total: null,
    currency: null,
    ...fields,
  },
  provenance: {},
  parser_version: null,
  input_method: "image",
  warnings: [],
});

describe("useReviewForm", () => {
  it("fills untouched fields when a pending revision becomes ready without changing its id", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReviewForm("doc-1", data),
      {
        initialProps: {
          data: {
            ...review(1),
            status: "pending" as const,
            fields: {
              ...review(1).fields,
              supplier_name: null,
              description: null,
              total: null,
              currency: null,
            },
          } as DocumentReview,
        },
      },
    );
    act(() => result.current.update("total", "99.99"));

    rerender({ data: review(1) });

    expect(result.current.form.total).toBe("99.99");
    expect(result.current.form.supplier_name).toBe("Sklep");
    expect(result.current.form.description).toBe("Zakupy");
  });

  it("applies later suggestions only to untouched fields and preserves account and category", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReviewForm("doc-1", data),
      { initialProps: { data: review(1) } },
    );
    act(() => {
      result.current.update("total", "99.99");
      result.current.update("payment_account_id", "account-1");
      result.current.update("category_id", "category-1");
    });

    rerender({
      data: {
        ...review(2, { total: "22.22", currency: "EUR" }),
        fields: {
          ...review(2).fields,
          supplier_name: "Nowy sklep",
          description: "Nowe zakupy",
          total: "22.22",
          currency: "EUR",
        },
      },
    });

    expect(result.current.form.total).toBe("99.99");
    expect(result.current.form.supplier_name).toBe("Nowy sklep");
    expect(result.current.form.payment_account_id).toBe("account-1");
    expect(result.current.form.category_id).toBe("category-1");
  });

  it("resets only when switching documents, not when refetching the current one", () => {
    const { result, rerender } = renderHook(
      ({ documentId, data }) => useReviewForm(documentId, data),
      { initialProps: { documentId: "doc-1", data: review(1) } },
    );
    act(() => result.current.update("total", "99.99"));
    rerender({ documentId: "doc-1", data: review(1) });
    expect(result.current.form.total).toBe("99.99");

    rerender({
      documentId: "doc-2",
      data: undefined as never,
    });
    expect(result.current.form.total).toBe("");
  });

  it("does not clear account or category when explicitly applying newer suggestions", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReviewForm("doc-1", data),
      { initialProps: { data: review(1) } },
    );
    act(() => {
      result.current.update("payment_account_id", "account-1");
      result.current.update("category_id", "category-1");
    });
    rerender({ data: review(2, { total: "22.22", currency: "EUR" }) });
    act(() => result.current.applyNewSuggestions());

    expect(result.current.form.payment_account_id).toBe("account-1");
    expect(result.current.form.category_id).toBe("category-1");
  });

  it("keeps dirty amount account and category while a pending review becomes ready at the same revision", () => {
    const { result, rerender } = renderHook(
      ({ data }) => useReviewForm("doc-1", data),
      {
        initialProps: {
          data: undefined as ReturnType<typeof review> | undefined,
        },
      },
    );
    act(() => {
      result.current.update("total", "99.99");
      result.current.update("payment_account_id", "account-1");
      result.current.update("category_id", "category-1");
    });
    rerender({ data: review(1) });
    expect(result.current.form.total).toBe("99.99");
    expect(result.current.form.payment_account_id).toBe("account-1");
    expect(result.current.form.category_id).toBe("category-1");
    expect(result.current.form.supplier_name).toBe("Sklep");
  });

  it("keeps a missing vision currency blank", () => {
    const { result } = renderHook(() =>
      useReviewForm("doc-1", review(1, { currency: null })),
    );
    expect(result.current.form.currency).toBe("");
  });
});

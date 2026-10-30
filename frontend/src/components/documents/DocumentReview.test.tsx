import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentReview } from "./DocumentReview";

const apiState = vi.hoisted(() => ({
  review: {
    id: "review-1",
    document_id: "document-1",
    revision: 1,
    status: "error",
    error_code: "provider_unavailable",
    document_type: "invoice",
    fields: {
      supplier_name: "Sklep",
      description: "Zakupy",
      total: "12.34",
      currency: "PLN",
    },
    provenance: { supplier_name: "ocr", total: "ocr" },
  } as unknown,
  prepare: vi.fn(),
  approve: vi.fn(),
}));

vi.mock("../../api/documents", () => ({
  useDocumentReview: () => ({
    data: apiState.review,
    isLoading: false,
    isError: false,
  }),
  usePrepareDocumentReview: () => ({
    mutate: apiState.prepare,
    isPending: false,
  }),
  useDocumentPreview: () => ({ data: undefined, isLoading: false }),
  useDocumentOriginal: () => ({ data: undefined, isLoading: false }),
}));
vi.mock("../../api/bills", () => ({
  usePrepareBill: () => ({ mutate: vi.fn(), isPending: false }),
  useApproveBill: () => ({ mutate: apiState.approve, isPending: false }),
  useAttachBillSource: () => ({ mutate: vi.fn(), isPending: false }),
}));

function renderReview() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DocumentReview documentId="document-1" onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("DocumentReview", () => {
  it("review_shows_llm_error_and_manual_fields", () => {
    renderReview();
    expect(screen.getByText(/zewnętrzny dostawca/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Sprzedawca")).toHaveValue("Sklep");
    expect(screen.getByLabelText("Kwota")).toHaveValue("12.34");
  });

  it("approve_has_no_payment_copy", () => {
    renderReview();
    expect(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Zarejestruj płatność|Wyślij przelew/i),
    ).not.toBeInTheDocument();
  });

  it("old_pdf_can_prepare_without_upload", () => {
    apiState.review = undefined;
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Sprawdź dane" }));
    expect(apiState.prepare).toHaveBeenCalledWith({
      documentId: "document-1",
      refresh: false,
    });
    apiState.review = {
      id: "review-1",
      document_id: "document-1",
      revision: 1,
      status: "error",
      error_code: "provider_unavailable",
      document_type: "invoice",
      fields: {
        supplier_name: "Sklep",
        description: "Zakupy",
        total: "12.34",
        currency: "PLN",
      },
      provenance: { supplier_name: "ocr", total: "ocr" },
    };
  });
});

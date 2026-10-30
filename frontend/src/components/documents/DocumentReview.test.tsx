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
  prepare: vi.fn((_input, options) =>
    options?.onSuccess?.({ id: "draft-1", version: 4 }),
  ),
  retryOcr: vi.fn(),
  attach: vi.fn(),
  approve: vi.fn(),
  approveError: null as unknown,
  prepareError: null as unknown,
  retryOcrError: null as unknown,
  navigate: vi.fn(),
  refetchBill: vi
    .fn()
    .mockResolvedValue({ data: { id: "draft-1", version: 5 } }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => apiState.navigate }));

vi.mock("../../api/documents", () => ({
  useDocumentReview: () => ({
    data: apiState.review,
    isLoading: false,
    isError: false,
  }),
  usePrepareDocumentReview: () => ({
    mutate: apiState.prepare,
    isPending: false,
    error: apiState.prepareError,
  }),
  useRetryDocumentOcr: () => ({
    mutate: apiState.retryOcr,
    isPending: false,
    error: apiState.retryOcrError,
  }),
  useDocumentPreview: () => ({ data: undefined, isLoading: false }),
  useDocumentOriginal: () => ({ data: undefined, isLoading: false }),
}));
vi.mock("../../api/bills", () => ({
  useSerializedIntentKey: () => () => "review-intent-key",
  usePrepareBill: () => ({ mutate: apiState.prepare, isPending: false }),
  useApproveBill: () => ({
    mutate: apiState.approve,
    isPending: false,
    error: apiState.approveError,
  }),
  useDuplicateCandidates: () => ({
    data: [{ id: "bill-existing", reasons: ["same_number"] }],
    isLoading: false,
  }),
  useBill: () => ({
    data: { id: "bill-existing", version: 9 },
    isLoading: false,
    refetch: apiState.refetchBill,
  }),
  useAttachBillSource: () => ({ mutate: apiState.attach, isPending: false }),
}));
vi.mock("../../api/finance", () => ({
  useCategories: () => ({
    data: [
      { id: "category-1", name: "Zakupy", type: "expense", is_active: true },
    ],
  }),
  useAccounts: () => ({
    data: [{ id: "account-1", name: "Karta", is_active: true }],
  }),
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

  it("offers explicit duplicate attach or separate approval with full manual fields", async () => {
    renderReview();
    fireEvent.change(screen.getByLabelText("Data sprzedaży"), {
      target: { value: "2026-10-02" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "category-1" },
    });
    fireEvent.change(screen.getByLabelText("Konto płatności"), {
      target: { value: "account-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    );
    expect(await screen.findByText(/podobny dokument/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Dołącz do istniejącego/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Zarejestruj osobno/ }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Data sprzedaży")).toBeInTheDocument();
    expect(screen.getByLabelText("Kategoria")).toBeInTheDocument();
    expect(screen.getByLabelText("Konto płatności")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zarejestruj osobno" }));
    expect(apiState.approve).toHaveBeenCalledWith(
      expect.objectContaining({
        billId: "draft-1",
        idempotencyKey: expect.any(String),
        data: expect.objectContaining({
          sale_date: "2026-10-02",
          category_id: "category-1",
          payment_account_id: "account-1",
          duplicate_decision: "separate",
        }),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Dołącz do istniejącego" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    );
    expect(apiState.attach).toHaveBeenCalledWith(
      expect.objectContaining({
        billId: "bill-existing",
        documentId: "document-1",
        expectedVersion: 9,
        idempotencyKey: expect.any(String),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("shows a distinct OCR retry action after an OCR error", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Ponów OCR" }));
    expect(apiState.retryOcr).toHaveBeenCalledWith({
      documentId: "document-1",
    });
  });

  it("shows separate prepare and OCR retry failures", () => {
    apiState.prepareError = new Error("prepare failed");
    apiState.retryOcrError = new Error("retry failed");
    renderReview();
    expect(
      screen.getByText(/Nie udało się przygotować przeglądu dokumentu/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Nie udało się ponowić OCR/i)).toBeInTheDocument();
    apiState.prepareError = null;
    apiState.retryOcrError = null;
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

  it("keeps manual fields visible and tells the reviewer to refresh after a 409 approval conflict", async () => {
    apiState.approve.mockImplementation((_input, options) => {
      apiState.approveError = {
        response: { status: 409, data: { detail: "version_conflict" } },
      };
      options?.onError?.(apiState.approveError);
    });
    const rendered = renderReview();
    fireEvent.change(screen.getByLabelText("Data sprzedaży"), {
      target: { value: "2026-10-03" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    );
    await screen.findByRole("button", { name: "Zarejestruj osobno" });
    fireEvent.click(screen.getByRole("button", { name: "Zarejestruj osobno" }));
    rendered.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <DocumentReview documentId="document-1" onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText(/Dane pozostały w formularzu; odśwież przegląd/),
    ).toHaveTextContent(
      /Dane pozostały w formularzu; odśwież przegląd i porównaj wersję dokumentu/,
    );
    expect(screen.getByLabelText("Data sprzedaży")).toHaveValue("2026-10-03");
    expect(
      screen.getByRole("button", { name: "Zarejestruj osobno" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    expect(
      screen.getByRole("button", { name: "Zarejestruj osobno" }),
    ).toBeEnabled();
    apiState.approveError = null;
    apiState.approve.mockReset();
  });

  it("blocks an attach conflict until a refreshed target version is acknowledged", async () => {
    apiState.attach.mockReset();
    apiState.attach.mockImplementation((_input, options) =>
      options?.onError?.({ response: { status: 409 } }),
    );
    renderReview();
    fireEvent.click(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    );
    await screen.findByRole("button", { name: "Dołącz do istniejącego" });
    fireEvent.click(
      screen.getByRole("button", { name: "Dołącz do istniejącego" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    );
    expect(apiState.attach).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    );
    expect(apiState.attach).toHaveBeenLastCalledWith(
      expect.objectContaining({ expectedVersion: 5 }),
      expect.anything(),
    );
    apiState.attach.mockReset();
  });

  it("opens the approved document register detail after a separate approval succeeds", async () => {
    apiState.approve.mockImplementation((_input, options) =>
      options?.onSuccess?.({ id: "approved-bill" }),
    );
    renderReview();
    fireEvent.click(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    );
    await screen.findByRole("button", { name: "Zarejestruj osobno" });
    fireEvent.click(screen.getByRole("button", { name: "Zarejestruj osobno" }));

    expect(apiState.navigate).toHaveBeenCalledWith(
      "/finances/documents?bill=approved-bill",
    );
    apiState.approve.mockReset();
  });
});

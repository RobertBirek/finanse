import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { categorySelectFixture } from "../../test/categoryFixtures";
import { describe, expect, it, vi } from "vitest";
import type { DocumentReview as DocumentReviewData } from "../../api/documents";
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
  } as unknown as DocumentReviewData | undefined,
  prepare: vi.fn((_input, options) =>
    options?.onSuccess?.({ id: "draft-1", version: 4 }),
  ),
  retryOcr: vi.fn(),
  prepareVision: vi.fn(),
  attach: vi.fn(),
  approve: vi.fn(),
  approveError: null as unknown,
  prepareError: null as unknown,
  retryOcrError: null as unknown,
  navigate: vi.fn(),
  archived: false,
  refetchBill: vi
    .fn()
    .mockResolvedValue({ data: { id: "draft-1", version: 5 } }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => apiState.navigate }));

vi.mock("../../api/documents", async (original) => ({
  ...(await original<typeof import("../../api/documents")>()),
  useDocumentMetadata: () => ({
    data: { archived_at: apiState.archived ? "2026-11-03T12:00:00Z" : null },
  }),
  useRestoreDocument: () => ({ mutate: vi.fn(), isPending: false }),
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
  usePrepareDocumentVision: () => ({
    mutate: apiState.prepareVision,
    isPending: false,
    error: null,
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
      {
        id: "category-1",
        name: "Zakupy",
        parent_id: null,
        type: "expense",
        is_active: true,
      },
      ...categorySelectFixture,
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
  it("uses sorted full category paths even if ancestors are archived", () => {
    renderReview();
    const select = screen.getByLabelText("Kategoria");
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "Nie wybieraj teraz",
      "Auto - Zamek",
      "Dom - Gaz",
      "Dom - Woda",
      "Zakupy",
    ]);
    fireEvent.change(select, { target: { value: "water" } });
    expect(select).toHaveValue("water");
  });
  it("does not animate archived pending history as current work", () => {
    const previous = apiState.review;
    apiState.archived = true;
    apiState.review = { ...previous!, status: "pending" };
    try {
      renderReview();
      expect(
        screen.queryByRole("status", { name: "Odczyt dokumentu" }),
      ).not.toBeInTheDocument();
    } finally {
      apiState.archived = false;
      apiState.review = previous;
    }
  });
  it("explains a stale processing action rejected because the document was archived", () => {
    apiState.prepareError = {
      response: { status: 409, data: { code: "document_archived" } },
    };
    try {
      renderReview();
      expect(
        screen.getByText(
          "Dokument jest w archiwum. Przywróć go przed nowym odczytem.",
        ),
      ).toBeVisible();
    } finally {
      apiState.prepareError = null;
    }
  });
  it("keeps archived original/history visible but disables new AI/OCR until restore", () => {
    const previous = apiState.review;
    apiState.archived = true;
    apiState.review = {
      ...previous!,
      input_method: "image",
      status: "incomplete",
      error_code: "attempts_exhausted",
      warnings: [],
    };
    try {
      renderReview();
      expect(
        screen.getByText(
          "Dokument jest w archiwum. Przywróć go przed nowym odczytem.",
        ),
      ).toBeVisible();
      expect(screen.getByRole("button", { name: "Ponów AI" })).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Ponów lokalny OCR" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Przywróć dokument" }),
      ).toBeEnabled();
    } finally {
      apiState.archived = false;
      apiState.review = previous;
    }
  });
  it.each(["pending", "processing"] as const)(
    "marks actual %s AI work inside the native document dialog",
    (status) => {
      const previous = apiState.review;
      apiState.review = { ...previous!, status, error_code: null };
      try {
        renderReview();
        expect(
          screen.getByRole("status", { name: "Odczyt dokumentu" }),
        ).toHaveTextContent(
          status === "pending" ? "AI w kolejce" : "AI pracuje",
        );
      } finally {
        apiState.review = previous;
      }
    },
  );
  it.each(["multiple", "unsupported", "statement", "loan_schedule"] as const)(
    "does not add unreadable-image retry for unsupported %s",
    (document_type) => {
      const previous = apiState.review;
      apiState.prepareVision.mockClear();
      apiState.review = {
        ...previous!,
        document_type,
        status: "incomplete",
        error_code: null,
        input_method: "image",
        warnings: ["unreadable"],
      };
      try {
        renderReview();
        expect(
          screen.queryByRole("button", { name: "Ponów AI" }),
        ).not.toBeInTheDocument();
        expect(apiState.prepareVision).not.toHaveBeenCalled();
      } finally {
        apiState.review = previous;
      }
    },
  );
  it("does not add unreadable-image retry for a text review", () => {
    const previous = apiState.review;
    apiState.review = {
      ...previous!,
      status: "incomplete",
      error_code: null,
      input_method: "text",
      warnings: ["unreadable"],
    };
    try {
      renderReview();
      expect(
        screen.queryByRole("button", { name: "Ponów AI" }),
      ).not.toBeInTheDocument();
    } finally {
      apiState.review = previous;
    }
  });
  it.each(["unreadable", "missing_required_fields"] as const)(
    "offers one explicit retry for an incomplete image with %s",
    (warning) => {
      const previous = apiState.review;
      apiState.prepareVision.mockClear();
      apiState.review = {
        ...previous!,
        status: "incomplete",
        error_code: null,
        input_method: "image",
        warnings: [warning],
      };
      try {
        renderReview();
        expect(
          screen.getByText(
            "AI nie odczytało wszystkich danych. Porównaj dokument z oryginałem, uzupełnij pola ręcznie lub jawnie ponów odczyt.",
          ),
        ).toBeInTheDocument();
        expect(screen.getByLabelText("Sprzedawca")).toHaveValue("Sklep");
        fireEvent.change(screen.getByLabelText("Opis"), {
          target: { value: "Ręcznie poprawiony opis" },
        });
        expect(apiState.prepareVision).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Ponów AI" }));
        expect(apiState.prepareVision).toHaveBeenCalledTimes(1);
        expect(apiState.prepareVision).toHaveBeenCalledWith(
          expect.objectContaining({
            documentId: "document-1",
            intentKey: expect.any(String),
          }),
        );
        expect(screen.getByLabelText("Opis")).toHaveValue(
          "Ręcznie poprawiony opis",
        );
      } finally {
        apiState.review = previous;
      }
    },
  );
  it.each(["pending", "processing", "ready"] as const)(
    "does not offer warning-based retry during %s",
    (status) => {
      const previous = apiState.review;
      apiState.prepareVision.mockClear();
      apiState.review = {
        ...previous!,
        status,
        error_code: null,
        input_method: "image",
        warnings: ["unreadable"],
      };
      try {
        renderReview();
        expect(
          screen.queryByRole("button", { name: "Ponów AI" }),
        ).not.toBeInTheDocument();
        expect(apiState.prepareVision).not.toHaveBeenCalled();
      } finally {
        apiState.review = previous;
      }
    },
  );
  it("allows an explicit retry of the legacy exhausted review without replaying it on mount", () => {
    const previous = apiState.review;
    apiState.prepareVision.mockClear();
    apiState.review = {
      ...previous!,
      status: "incomplete",
      error_code: "attempts_exhausted",
    };
    try {
      renderReview();
      expect(apiState.prepareVision).not.toHaveBeenCalled();
      expect(screen.getByLabelText("Sprzedawca")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Ponów AI" }));
      expect(apiState.prepareVision).toHaveBeenCalledTimes(1);
    } finally {
      apiState.review = previous;
    }
  });
  it.each(["incomplete", "error"] as const)(
    "explains invalid model output without automatically retrying (%s)",
    (status) => {
      const previous = apiState.review;
      apiState.prepareVision.mockClear();
      apiState.review = {
        ...previous!,
        status,
        error_code: "invalid_model_output",
      };
      try {
        renderReview();
        expect(
          screen.getByText(
            "AI zwróciło niepoprawne dane. Możesz uzupełnić pola ręcznie.",
          ),
        ).toBeInTheDocument();
        expect(screen.getByLabelText("Sprzedawca")).toBeInTheDocument();
        expect(apiState.prepareVision).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Ponów AI" }));
        expect(apiState.prepareVision).toHaveBeenCalledTimes(1);
      } finally {
        apiState.review = previous;
      }
    },
  );
  it("review_shows_llm_error_and_manual_fields", () => {
    renderReview();
    expect(screen.getByText(/zewnętrzny dostawca/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Sprzedawca")).toHaveValue("Sklep");
    expect(screen.getByLabelText("Kwota")).toHaveValue("12.34");
  });

  it("keeps the manual form available for a failed other placeholder", () => {
    const current = apiState.review!;
    apiState.review = {
      ...current,
      document_type: "other",
      status: "error",
    };
    renderReview();
    expect(screen.getByLabelText("Sprzedawca")).toBeInTheDocument();
    apiState.review = {
      ...current,
      document_type: "invoice",
    };
  });

  it("keeps the manual form available for a ready other review", () => {
    const current = apiState.review!;
    apiState.review = {
      ...current,
      document_type: "other",
      status: "ready",
    };
    renderReview();
    expect(screen.getByLabelText("Sprzedawca")).toBeInTheDocument();
    apiState.review = current;
  });

  it("keeps a genuine unsupported review out of the manual register form", () => {
    const current = apiState.review!;
    apiState.review = {
      ...current,
      document_type: "unsupported",
      status: "ready",
    };
    renderReview();
    expect(screen.queryByLabelText("Sprzedawca")).not.toBeInTheDocument();
    expect(
      screen.getByText(/nie jest fakturą\/paragonem/i),
    ).toBeInTheDocument();
    apiState.review = current;
  });

  it("leaves a missing currency unselected and blocks preparation", () => {
    const current = apiState.review!;
    apiState.review = {
      ...current,
      fields: { ...current.fields, currency: null },
    };
    renderReview();
    expect(screen.getByLabelText("Waluta")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    ).toBeDisabled();
    apiState.review = {
      ...current,
      fields: { ...current.fields, currency: "PLN" },
    };
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

  it("offers separate AI and local OCR retries after an AI error", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: "Ponów AI" }));
    fireEvent.click(screen.getByRole("button", { name: "Ponów lokalny OCR" }));
    expect(apiState.prepareVision).toHaveBeenCalledWith(
      expect.objectContaining({ documentId: "document-1" }),
    );
    expect(apiState.retryOcr).toHaveBeenCalledWith(
      expect.objectContaining({ documentId: "document-1" }),
    );
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
    } as unknown as DocumentReviewData;
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

  it("requires a target refetch after attach 409 even when a draft conflict was acknowledged", async () => {
    apiState.approve.mockImplementation((_input, options) =>
      options?.onError?.({ response: { status: 409 } }),
    );
    apiState.attach.mockImplementation((_input, options) =>
      options?.onError?.({ response: { status: 409 } }),
    );
    apiState.refetchBill
      .mockReset()
      .mockResolvedValueOnce({ data: { id: "draft-1", version: 5 } })
      .mockResolvedValueOnce({ data: { id: "bill-existing", version: 6 } });
    renderReview();
    fireEvent.click(
      screen.getByRole("button", { name: "Zatwierdź do rejestru" }),
    );
    await screen.findByRole("button", { name: "Zarejestruj osobno" });
    fireEvent.click(screen.getByRole("button", { name: "Zarejestruj osobno" }));
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 5/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Dołącz do istniejącego" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    );
    expect(
      screen.queryByRole("button", { name: /podejmuję nową decyzję/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Odśwież aktualny dokument/ }),
    );
    await screen.findByText(/Aktualna wersja: 6/);
    fireEvent.click(
      screen.getByRole("button", { name: /podejmuję nową decyzję/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź dołączenie" }),
    );
    expect(apiState.attach).toHaveBeenLastCalledWith(
      expect.objectContaining({ expectedVersion: 6 }),
      expect.anything(),
    );
    apiState.approve.mockReset();
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

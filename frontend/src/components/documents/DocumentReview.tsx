import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  useApproveBill,
  useAttachBillSource,
  useBill,
  usePrepareBill,
  useSerializedIntentKey,
  type BillApprove,
  type BillComparisonFields,
  type BillResponse,
  type DuplicateCandidate,
} from "../../api/bills";
import {
  useDocumentOriginal,
  useDocumentPreview,
  useDocumentReview,
  useSuggestDocumentCategory,
  usePrepareDocumentReview,
  usePrepareDocumentVision,
  useRetryDocumentOcr,
  useDocumentMetadata,
  useRestoreDocument,
  documentArchiveError,
} from "../../api/documents";
import { useAccounts, useCategories, type Category } from "../../api/finance";
import { categoryOptions, categoryPath } from "../../lib/categories";
import { formatCalendarDate } from "../../lib/date";
import { Dialog } from "../Dialog";
import { DocumentIcon, DocumentTooltip } from "./documentControls";
import type { AxiosError } from "axios";
import { useReviewForm, type ReviewForm } from "./useReviewForm";
import { useAuthStore } from "../../stores/authStore";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
  useDocumentProcessingStore,
} from "../../stores/documentProcessingStore";

type Props = { documentId: string; onClose: () => void };
type Draft = { id: string; version: number };
type ApprovalFields = Omit<BillApprove, "version" | "duplicate_decision">;
type ApprovalError = AxiosError<{
  detail?: string;
  duplicate_candidates?: DuplicateCandidate[];
}>;
function parseAmount(raw: string): number | null {
  const match =
    /^(\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:[.,](\d{1,2}))?$/.exec(
      raw.trim(),
    );
  if (!match) return null;
  const digits = match[1].replace(/\s/g, "");
  const cents = Number(digits + (match[2] ?? "").padEnd(2, "0"));
  return Number.isSafeInteger(cents) && cents > 0 ? cents : null;
}
const mutationError = (error: unknown) => {
  const detail = (error as AxiosError<{ detail?: unknown }>)?.response?.data
    ?.detail;
  if (detail === "duplicate_decision_required")
    return "Wykryto podobny dokument. Nie udało się wyświetlić porównania.";
  return typeof detail === "string"
    ? detail
    : "Nie udało się zapisać zmian. Popraw pola i spróbuj ponownie.";
};
const processingError = (error: unknown, fallback: string) => {
  const data = (error as AxiosError<{ code?: string; detail?: string }>)
    ?.response?.data;
  const code = data?.code ?? data?.detail;
  return code === "document_archived" || code === "document_processing_active"
    ? documentArchiveError(error)
    : fallback;
};

function categorySuggestionError(error: unknown): string {
  const response = (error as AxiosError<{ detail?: string }>)?.response;
  if (response?.status === 429)
    return "Za dużo prób. Odczekaj chwilę lub wybierz kategorię ręcznie.";
  if (
    response?.status === 404 ||
    response?.data?.detail === "category_read_unavailable"
  )
    return "Zapisany odczyt jest niedostępny. Odśwież dokument lub wybierz kategorię ręcznie.";
  return processingError(
    error,
    "Nie udało się podpowiedzieć kategorii. Spróbuj ponownie lub wybierz kategorię ręcznie.",
  );
}

export function DocumentReview({ documentId, onClose }: Props) {
  const ownerId = useAuthStore((state) => state.user?.id);
  const generation = useDocumentProcessingStore((state) => state.generation);
  return (
    <DocumentReviewContent
      key={`${ownerId}:${generation}:${documentId}`}
      documentId={documentId}
      onClose={onClose}
    />
  );
}

function DocumentReviewContent({ documentId, onClose }: Props) {
  const navigate = useNavigate();
  const metadata = useDocumentMetadata(documentId);
  const [showLatest, setShowLatest] = useState(false);
  const [manualEntry, setManualEntry] = useState(false);
  const [mobilePane, setMobilePane] = useState<"original" | "data">("data");
  const pinnedRevision =
    metadata.data?.finance?.bill_id && !showLatest
      ? metadata.data.finance.revision_id
      : null;
  const review = useDocumentReview(documentId, pinnedRevision);
  const restore = useRestoreDocument();
  const archived = !!metadata.data?.archived_at;
  const canProcess =
    !!metadata.data && !Array.isArray(metadata.data) && !archived;
  const canRegister =
    canProcess && metadata.data?.finance?.review !== "approved";
  const preview = useDocumentPreview(documentId);
  const original = useDocumentOriginal(documentId);
  const prepare = usePrepareDocumentReview();
  const prepareVision = usePrepareDocumentVision();
  const retryOcr = useRetryDocumentOcr();
  const prepareBill = usePrepareBill();
  const approve = useApproveBill();
  const attach = useAttachBillSource();
  const keyFor = useSerializedIntentKey();
  const [draftBill, setDraftBill] = useState<Draft | null>(null);
  const [duplicateReview, setDuplicateReview] = useState<{
    candidates: DuplicateCandidate[];
    fields: ApprovalFields;
    formKey: string;
  } | null>(null);
  const [attachTargetId, setAttachTargetId] = useState<string | null>(null);
  const attachTarget = useBill(attachTargetId);
  const [attachComparison, setAttachComparison] = useState<BillResponse | null>(
    null,
  );
  const comparedTarget = attachComparison ?? attachTarget.data;
  const currentDraft = useBill(draftBill?.id ?? null, false);
  const categories = useCategories();
  const accounts = useAccounts();
  const suggestCategory = useSuggestDocumentCategory();
  const savedRead = review.data;
  const categoryRead =
    canRegister &&
    metadata.data?.processing_method !== "bank_import" &&
    !review.isError &&
    savedRead &&
    (savedRead.status === "ready" || savedRead.status === "incomplete") &&
    (savedRead.document_type === "invoice" ||
      savedRead.document_type === "receipt") &&
    (savedRead.fields.supplier_name?.trim() ||
      savedRead.fields.description?.trim())
      ? savedRead
      : undefined;
  const categoryRequestMatches =
    categoryRead && suggestCategory.variables?.revisionId === categoryRead.id;
  const requestedCategoryId = categoryRequestMatches
    ? suggestCategory.data?.suggested_category_id
    : undefined;
  const categoryFromHistory = suggestCategory.data?.source === "history";
  const requestedCategory = categories.data?.find(
    (item) =>
      item.id === requestedCategoryId &&
      item.is_active &&
      item.type === "expense",
  );
  const { form, update, applyNewSuggestions } = useReviewForm(
    documentId,
    metadata.isLoading ? undefined : review.data,
    categories.data,
    requestedCategory?.id,
  );
  const formKey = JSON.stringify(form);
  const amount = parseAmount(form.total);
  const matchingDuplicates =
    duplicateReview?.formKey === formKey ? duplicateReview : null;
  const [conflict, setConflict] = useState<"draft" | "attach" | null>(null);
  const [refreshedConflict, setRefreshedConflict] = useState<
    "draft" | "attach" | null
  >(null);
  const [conflictRefreshFailed, setConflictRefreshFailed] = useState(false);
  const previewUrl = useMemo(
    () => (preview.data ? URL.createObjectURL(preview.data) : null),
    [preview.data],
  );
  const originalUrl = useMemo(
    () => (original.data ? URL.createObjectURL(original.data) : null),
    [original.data],
  );
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );
  useEffect(
    () => () => {
      if (originalUrl) URL.revokeObjectURL(originalUrl);
    },
    [originalUrl],
  );
  const invalidModelOutput =
    (review.data?.status === "error" || review.data?.status === "incomplete") &&
    review.data.error_code === "invalid_model_output";
  const interruptedModelRead =
    review.data?.status === "incomplete" &&
    review.data.error_code === "attempts_exhausted";
  const unsupported =
    review.data?.status !== "error" &&
    review.data?.status !== "pending" &&
    review.data?.status !== "processing" &&
    (review.data?.document_type === "multiple" ||
      review.data?.document_type === "unsupported" ||
      review.data?.document_type === "statement" ||
      review.data?.document_type === "loan_schedule");
  const incompleteImageRead =
    review.data?.status === "incomplete" &&
    review.data.input_method === "image" &&
    !review.data.error_code &&
    !unsupported &&
    review.data.warnings.some(
      (warning) =>
        warning === "unreadable" || warning === "missing_required_fields",
    );
  const isPdf = metadata.data?.mime_type === "application/pdf";
  const needsPdfOcr =
    isPdf &&
    (metadata.data?.status === "error" ||
      review.data?.error_code === "ocr_text_unavailable");
  const pdfProcessing =
    isPdf &&
    (metadata.data?.status === "pending" ||
      metadata.data?.status === "processing" ||
      review.data?.status === "pending" ||
      review.data?.status === "processing");
  const retryLocalOcr = (
    <button
      type="button"
      className="btn-secondary ml-2"
      disabled={!canProcess || pdfProcessing || retryOcr.isPending}
      onClick={() =>
        retryOcr.mutate({ documentId, intentKey: crypto.randomUUID() })
      }
    >
      Ponów lokalny OCR
    </button>
  );
  const submitApproval = (
    draft: Draft,
    fields: ApprovalFields,
    submittedFormKey: string,
    separate = false,
  ) => {
    const data: BillApprove = {
      ...fields,
      version: draft.version,
      ...(separate ? { duplicate_decision: "separate" as const } : {}),
    };
    const actor = captureProcessingActor();
    approve.mutate(
      {
        billId: draft.id,
        data,
        idempotencyKey: keyFor({
          action: "approve-bill",
          billId: draft.id,
          data,
        }),
      },
      {
        onSuccess: (bill) => {
          if (isProcessingActorCurrent(actor))
            navigate(`/finances/documents?bill=${bill.id}`);
        },
        onError: (error) => {
          if (!isProcessingActorCurrent(actor)) return;
          const response = (error as ApprovalError).response;
          if (
            response?.status === 422 &&
            response.data?.detail === "duplicate_decision_required"
          ) {
            const candidates = response.data.duplicate_candidates;
            if (Array.isArray(candidates) && candidates.length > 0) {
              setAttachTargetId(null);
              setAttachComparison(null);
              setDuplicateReview({
                candidates,
                fields,
                formKey: submittedFormKey,
              });
            }
          } else if (response?.status === 409) {
            setRefreshedConflict(null);
            setConflictRefreshFailed(false);
            setConflict("draft");
          }
        },
      },
    );
  };

  const approvalPending =
    prepareBill.isPending || approve.isPending || attach.isPending;
  const approvalResponse = (approve.error as ApprovalError | null)?.response;
  const approvalFailure =
    approvalResponse?.data?.detail === "duplicate_decision_required" &&
    duplicateReview
      ? null
      : approve.error;
  const registrationError =
    prepareBill.error || approvalFailure || attach.error;

  const submit = () => {
    if (!canRegister || approvalPending || conflict || matchingDuplicates)
      return;
    if (
      amount === null ||
      !form.supplier_name.trim() ||
      !form.description.trim() ||
      !form.currency
    )
      return;
    const fields: ApprovalFields = {
      kind: form.kind,
      supplier_name: form.supplier_name.trim(),
      description: form.description.trim(),
      total_minor: amount,
      currency: form.currency,
      declaration: form.kind === "receipt" ? "declared_paid" : "unknown",
      supplier_tax_id: form.supplier_tax_id || null,
      number: form.number || null,
      issue_date: form.issue_date || null,
      sale_date: form.sale_date || null,
      due_date: form.due_date || null,
      payee_iban: form.payee_iban || null,
      category_id: form.category_id || null,
      payment_account_id: form.payment_account_id || null,
    };
    setDuplicateReview(null);
    setAttachTargetId(null);
    setAttachComparison(null);
    if (draftBill) {
      submitApproval(draftBill, fields, formKey);
      return;
    }
    const actor = captureProcessingActor();
    prepareBill.mutate(
      { documentId },
      {
        onSuccess: (bill) => {
          if (!isProcessingActorCurrent(actor)) return;
          const draft = { id: bill.id, version: bill.version };
          setDraftBill(draft);
          submitApproval(draft, fields, formKey);
        },
      },
    );
  };
  return (
    <Dialog
      label="Sprawdź dane dokumentu"
      onClose={onClose}
      panelClassName="w-full max-w-4xl rounded-xl border border-gray-700 bg-gray-900"
      busy={
        prepare.isPending ||
        retryOcr.isPending ||
        prepareVision.isPending ||
        prepareBill.isPending ||
        approve.isPending ||
        attach.isPending
      }
    >
      <div className="sticky top-0 z-10 border-b border-gray-800 bg-gray-900 px-4 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-white">Sprawdź dane</h2>
            {metadata.data?.original_name && (
              <p
                className="truncate text-xs text-gray-400"
                title={metadata.data.original_name}
              >
                {metadata.data.original_name}
              </p>
            )}
          </div>
          <DocumentTooltip label="Zamknij">
            <button
              type="button"
              aria-label="Zamknij"
              onClick={onClose}
              className="document-icon-control"
            >
              <DocumentIcon name="close" />
            </button>
          </DocumentTooltip>
        </div>
        <div
          role="group"
          aria-label="Widok dokumentu"
          className="mt-1 grid grid-cols-2 gap-1 rounded-lg bg-gray-950 p-1 md:hidden"
        >
          {(["original", "data"] as const).map((pane) => (
            <button
              key={pane}
              type="button"
              aria-pressed={mobilePane === pane}
              onClick={() => setMobilePane(pane)}
              className={`min-h-11 rounded-md px-2 text-sm font-medium ${mobilePane === pane ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white"}`}
            >
              {pane === "original" ? "Oryginał" : "Dane"}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-5 p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {archived && (
          <div className="md:col-span-2 rounded border border-gray-700 p-3 text-sm text-gray-300">
            <p>Dokument jest w archiwum. Przywróć go przed nowym odczytem.</p>
            <button
              type="button"
              className="btn-secondary mt-2"
              disabled={restore.isPending}
              onClick={() => restore.mutate({ documentId })}
            >
              Przywróć dokument
            </button>
            {restore.isError && (
              <p role="alert">{documentArchiveError(restore.error)}</p>
            )}
          </div>
        )}
        <div className="md:col-span-2">
          <DocumentProcessingInline
            documentId={documentId}
            review={archived ? undefined : review.data}
          />
        </div>
        <section
          aria-label="Oryginał dokumentu"
          className={`min-w-0 self-start rounded-lg border border-gray-800 bg-gray-950 p-3 md:block ${mobilePane === "original" ? "" : "hidden"}`}
        >
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-medium text-white">Oryginał dokumentu</h3>
            {originalUrl && (
              <DocumentTooltip label="Pobierz oryginał">
                <a
                  href={originalUrl}
                  download="dokument"
                  aria-label="Pobierz autoryzowany oryginał"
                  className="document-icon-control"
                >
                  <DocumentIcon name="download" />
                </a>
              </DocumentTooltip>
            )}
          </div>
          {previewUrl ? (
            preview.data?.type === "application/pdf" ? (
              <iframe
                src={previewUrl}
                title="Autoryzowany podgląd PDF"
                className="mt-3 h-96 w-full rounded-lg bg-white"
              />
            ) : (
              <img
                src={previewUrl}
                alt="Autoryzowany podgląd dokumentu"
                className="mt-3 max-h-[24rem] w-full object-contain"
              />
            )
          ) : preview.isError ? (
            <p className="mt-3 text-sm text-gray-300">
              Nie udało się załadować podglądu.{" "}
              {originalUrl
                ? "Możesz pobrać oryginał."
                : "Spróbuj otworzyć dokument ponownie."}
            </p>
          ) : (
            <p role="status" className="mt-3 text-sm text-gray-400">
              Ładowanie podglądu…
            </p>
          )}
        </section>
        <section
          aria-label="Dane dokumentu"
          className={`min-w-0 md:block ${mobilePane === "data" ? "" : "hidden"}`}
        >
          {prepare.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {processingError(
                prepare.error,
                "Nie udało się przygotować przeglądu dokumentu. Spróbuj ponownie.",
              )}
            </p>
          ) : null}
          {retryOcr.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {processingError(
                retryOcr.error,
                "Nie udało się ponowić OCR. Możesz poprawić pola ręcznie.",
              )}
            </p>
          ) : null}
          {prepareVision.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {processingError(
                prepareVision.error,
                "Nie udało się ponowić AI. Możesz poprawić pola ręcznie.",
              )}
            </p>
          ) : null}
          {registrationError ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {mutationError(registrationError)}
              {approvalResponse?.status === 409 ||
              (attach.error as AxiosError | null)?.response?.status === 409
                ? " Dane pozostały w formularzu; odśwież przegląd i porównaj wersję dokumentu przed kolejną próbą."
                : ""}
            </p>
          ) : null}
          {conflict ? (
            <div className="mb-3 rounded border border-amber-700 p-3 text-sm text-amber-100">
              Wersja przed zmianą:{" "}
              {conflict === "draft"
                ? draftBill?.version
                : attachTarget.data?.version}
              .
              {refreshedConflict === conflict
                ? ` Aktualna wersja: ${
                    conflict === "draft"
                      ? draftBill?.version
                      : attachComparison?.version
                  }.`
                : ""}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={
                    conflict === "draft"
                      ? currentDraft.isFetching
                      : attachTarget.isFetching
                  }
                  onClick={async () => {
                    setConflictRefreshFailed(false);
                    const result =
                      conflict === "draft"
                        ? await currentDraft.refetch()
                        : await attachTarget.refetch();
                    const expectedId =
                      conflict === "draft" ? draftBill?.id : attachTargetId;
                    if (
                      !result.isError &&
                      result.data &&
                      result.data.id === expectedId
                    ) {
                      setRefreshedConflict(conflict);
                      if (conflict === "draft" && draftBill)
                        setDraftBill({
                          ...draftBill,
                          version: result.data.version,
                        });
                      if (conflict === "attach")
                        setAttachComparison(result.data);
                    } else {
                      setRefreshedConflict(null);
                      setConflictRefreshFailed(true);
                    }
                  }}
                >
                  Odśwież aktualny dokument
                </button>
                {refreshedConflict === conflict ? (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setConflict(null)}
                  >
                    Rozumiem — podejmuję nową decyzję
                  </button>
                ) : null}
              </div>
              {conflictRefreshFailed && (
                <p role="alert" className="mt-2">
                  Nie udało się odświeżyć wpisu. Spróbuj ponownie.
                </p>
              )}
            </div>
          ) : null}
          {review.isError || !review.data ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-secondary"
                disabled={!canProcess || prepare.isPending}
                onClick={() => {
                  setShowLatest(true);
                  prepare.mutate({ documentId, refresh: false });
                }}
              >
                Sprawdź dane
              </button>
              {canRegister && !manualEntry && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setManualEntry(true)}
                >
                  Wpisz ręcznie
                </button>
              )}
              {needsPdfOcr && retryLocalOcr}
            </div>
          ) : (
            <>
              <p className="text-sm text-gray-400">
                OCR i zewnętrzny dostawca językowy mogą się pomylić. Porównaj
                dane z oryginałem i popraw je ręcznie.
              </p>
              {pinnedRevision && (
                <p className="mt-2 text-xs text-gray-400">
                  Wyświetlasz odczyt użyty do szkicu.
                  <button
                    type="button"
                    className="ml-2 underline"
                    onClick={() => setShowLatest(true)}
                  >
                    Pokaż najnowsze sugestie bez ponownego odczytu
                  </button>
                </p>
              )}
              {(review.data.status === "error" ||
                invalidModelOutput ||
                interruptedModelRead ||
                incompleteImageRead ||
                needsPdfOcr) && (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  {invalidModelOutput
                    ? "AI zwróciło niepoprawne dane. Możesz uzupełnić pola ręcznie."
                    : incompleteImageRead
                      ? "AI nie odczytało wszystkich danych. Porównaj dokument z oryginałem, uzupełnij pola ręcznie lub jawnie ponów odczyt."
                      : needsPdfOcr
                        ? "Odczyt tego PDF wymaga sprawdzenia. Możesz ponowić lokalny OCR lub uzupełnić pola ręcznie."
                        : "Nie udało się uzyskać propozycji od zewnętrznego dostawcy. Możesz uzupełnić pola ręcznie."}
                  {(!isPdf || metadata.data?.has_extracted_text) && (
                    <button
                      type="button"
                      className="btn-secondary ml-2"
                      disabled={
                        !canProcess ||
                        pdfProcessing ||
                        prepare.isPending ||
                        prepareVision.isPending
                      }
                      onClick={() => {
                        setShowLatest(true);
                        if (isPdf) {
                          prepare.mutate({ documentId, refresh: true });
                        } else {
                          prepareVision.mutate({
                            documentId,
                            intentKey: crypto.randomUUID(),
                          });
                        }
                      }}
                    >
                      {isPdf ? "Ponów analizę tekstu" : "Ponów AI"}
                    </button>
                  )}
                  {retryLocalOcr}
                </p>
              )}
              {unsupported && (
                <p role="alert" className="mt-3 text-sm text-yellow-300">
                  Ten dokument zawiera wiele pozycji albo nie jest
                  fakturą/paragonem. Nie trafia do rejestru finansowego jako
                  jedna pozycja.
                </p>
              )}
              {review.data.revision > 1 && !unsupported ? (
                <button
                  type="button"
                  className="btn-secondary mt-2"
                  onClick={applyNewSuggestions}
                >
                  Zastosuj nowe sugestie
                </button>
              ) : null}
            </>
          )}
          {!unsupported && (manualEntry || review.data) && (
            <ReviewForm
              form={form}
              update={update}
              provenance={review.data?.provenance ?? {}}
              onSubmit={submit}
              pending={approvalPending}
              focusSupplier={manualEntry}
              canRegister={canRegister}
              hasValidAmount={amount !== null}
              submitBlocked={!!conflict || !!matchingDuplicates}
              categories={categories.data ?? []}
              accounts={accounts.data ?? []}
              categoryAction={
                categoryRead && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={suggestCategory.isPending}
                      onClick={() =>
                        suggestCategory.mutate({
                          documentId,
                          revisionId: categoryRead.id,
                        })
                      }
                    >
                      {suggestCategory.isPending
                        ? "Dobieranie kategorii…"
                        : "Podpowiedz kategorię"}
                    </button>
                    <p className="text-xs text-gray-400">
                      Najpierw sprawdzimy wcześniejsze zatwierdzenia dostawcy.
                      Gdy historia nie wystarczy, AI otrzyma sprzedawcę i opis z
                      odczytu oraz nazwy Twoich kategorii wydatków.
                    </p>
                    {categoryRequestMatches && suggestCategory.isPending && (
                      <p role="status" className="sr-only">
                        Trwa dobieranie kategorii.
                      </p>
                    )}
                    {categoryRequestMatches && suggestCategory.isError && (
                      <p role="alert" className="text-sm text-red-300">
                        {categorySuggestionError(suggestCategory.error)}
                      </p>
                    )}
                    {categoryRequestMatches && suggestCategory.isSuccess && (
                      <p role="status" className="text-sm text-gray-300">
                        {requestedCategory
                          ? `${categoryFromHistory ? "Z historii zatwierdzeń" : "Propozycja AI"} — ${categoryPath(requestedCategory.id, categories.data ?? [])}`
                          : "Brak pasującej kategorii. Możesz wybrać ją ręcznie."}
                        {requestedCategory &&
                          categoryFromHistory &&
                          suggestCategory.data?.history_count != null && (
                            <span className="block text-xs text-gray-400">
                              Na podstawie {suggestCategory.data.history_count}{" "}
                              zatwierdzonych dokumentów.
                            </span>
                          )}
                      </p>
                    )}
                  </div>
                )
              }
            />
          )}
          {draftBill && matchingDuplicates && (
            <DuplicateChoices
              candidates={matchingDuplicates.candidates}
              current={matchingDuplicates.fields}
              selectedId={attachTargetId}
              onAttach={(candidate) => {
                if (candidate.id === attachTargetId) {
                  if (attachTarget.isError) void attachTarget.refetch();
                  return;
                }
                setAttachComparison(null);
                setAttachTargetId(candidate.id);
              }}
              attachTarget={
                comparedTarget?.id === attachTargetId
                  ? comparedTarget
                  : undefined
              }
              attachTargetLoading={attachTarget.isFetching}
              attachTargetError={attachTarget.isError}
              onConfirmAttach={(target) =>
                attach.mutate(
                  {
                    billId: target.id,
                    documentId,
                    expectedVersion: target.version,
                    idempotencyKey: keyFor({
                      action: "attach-bill-source",
                      billId: target.id,
                      documentId,
                      expectedVersion: target.version,
                    }),
                  },
                  {
                    onSuccess: (bill) =>
                      navigate(`/finances/documents?bill=${bill.id}`),
                    onError: (error) => {
                      if ((error as AxiosError).response?.status === 409) {
                        setAttachComparison(null);
                        setRefreshedConflict(null);
                        setConflictRefreshFailed(false);
                        setConflict("attach");
                      }
                    },
                  },
                )
              }
              onSeparate={() =>
                submitApproval(
                  draftBill,
                  matchingDuplicates.fields,
                  formKey,
                  true,
                )
              }
              disabled={!canRegister || !!conflict || approvalPending}
            />
          )}
        </section>
      </div>
    </Dialog>
  );
}

function ReviewForm({
  form,
  update,
  provenance,
  onSubmit,
  pending,
  focusSupplier,
  canRegister,
  hasValidAmount,
  submitBlocked,
  categories,
  accounts,
  categoryAction,
}: {
  form: ReviewForm;
  update: (key: keyof ReviewForm, value: string) => void;
  provenance: Record<string, string>;
  onSubmit: () => void;
  pending: boolean;
  focusSupplier: boolean;
  canRegister: boolean;
  hasValidAmount: boolean;
  submitBlocked: boolean;
  categories: Category[];
  accounts: { id: string; name: string; is_active: boolean }[];
  categoryAction?: ReactNode;
}) {
  const [validateAmount, setValidateAmount] = useState(false);
  return (
    <form
      className="mt-4"
      aria-busy={pending}
      onSubmit={(event) => {
        event.preventDefault();
        setValidateAmount(true);
        onSubmit();
      }}
    >
      <fieldset
        disabled={pending || !canRegister}
        className="min-w-0 space-y-3"
      >
        <label className="block text-sm text-gray-300">
          Typ
          <select
            aria-label="Typ"
            value={form.kind}
            onChange={(e) => update("kind", e.target.value)}
            className="input mt-1 w-full"
          >
            <option value="invoice">Faktura</option>
            <option value="receipt">Paragon</option>
          </select>
        </label>
        <Field
          label="Sprzedawca"
          value={form.supplier_name}
          onChange={(v) => update("supplier_name", v)}
          note={provenance.supplier_name}
          autoFocus={focusSupplier}
          required
        />
        <Field
          label="Data sprzedaży"
          value={form.sale_date}
          onChange={(v) => update("sale_date", v)}
          type="date"
        />
        <Field
          label="Opis"
          value={form.description}
          onChange={(v) => update("description", v)}
          required
        />
        <label className="block text-sm text-gray-300">
          Kategoria
          <select
            aria-label="Kategoria"
            value={form.category_id}
            onChange={(e) => update("category_id", e.target.value)}
            className="input mt-1 w-full"
          >
            <option value="">Nie wybieraj teraz</option>
            {categoryOptions(categories)
              .filter((item) => item.is_active && item.type === "expense")
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
          </select>
        </label>
        {categoryAction}
        <label className="block text-sm text-gray-300">
          Konto płatności
          <select
            aria-label="Konto płatności"
            value={form.payment_account_id}
            onChange={(e) => update("payment_account_id", e.target.value)}
            className="input mt-1 w-full"
          >
            <option value="">Nie wybieraj teraz</option>
            {accounts
              .filter((item) => item.is_active)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </label>
        <Field
          label="Kwota"
          value={form.total}
          onChange={(v) => update("total", v)}
          onBlur={() => setValidateAmount(true)}
          inputMode="decimal"
          error={
            validateAmount && !hasValidAmount
              ? "Wpisz poprawną kwotę większą od zera, np. 123,45."
              : undefined
          }
          note={provenance.total}
          required
        />
        <label className="block text-sm text-gray-300">
          Waluta
          <select
            aria-label="Waluta"
            value={form.currency}
            onChange={(e) => update("currency", e.target.value)}
            className="input mt-1 w-full"
          >
            <option value="">Wybierz walutę</option>
            <option>PLN</option>
            <option>EUR</option>
            <option>USD</option>
          </select>
        </label>
        <Field
          label="Data wystawienia"
          value={form.issue_date}
          onChange={(v) => update("issue_date", v)}
          type="date"
        />
        <Field
          label="Termin płatności"
          value={form.due_date}
          onChange={(v) => update("due_date", v)}
          type="date"
        />
        <Field
          label="Numer dokumentu"
          value={form.number}
          onChange={(v) => update("number", v)}
        />
        <Field
          label="NIP sprzedawcy"
          value={form.supplier_tax_id}
          onChange={(v) => update("supplier_tax_id", v)}
        />
        <Field
          label="IBAN odbiorcy"
          value={form.payee_iban}
          onChange={(v) => update("payee_iban", v)}
        />
        <p className="text-xs text-gray-400">
          Kategoria i konto płatności są opcjonalne.
        </p>
        <button
          type="submit"
          disabled={submitBlocked || !form.currency}
          className="btn-primary"
        >
          {pending ? "Zapisywanie…" : "Zatwierdź do rejestru"}
        </button>
      </fieldset>
    </form>
  );
}

function DuplicateChoices({
  candidates,
  current,
  selectedId,
  onAttach,
  attachTarget,
  attachTargetLoading,
  attachTargetError,
  onConfirmAttach,
  onSeparate,
  disabled,
}: {
  candidates: DuplicateCandidate[];
  current: ApprovalFields;
  selectedId: string | null;
  onAttach: (candidate: DuplicateCandidate) => void;
  attachTarget?: BillResponse;
  attachTargetLoading: boolean;
  attachTargetError: boolean;
  onConfirmAttach: (target: { id: string; version: number }) => void;
  onSeparate: () => void;
  disabled: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const prefix = useId();
  useEffect(() => heading.current?.focus(), []);
  const canAttach =
    attachTarget?.lifecycle === "active" && attachTarget.review === "approved";
  return (
    <section
      aria-labelledby={`${prefix}-heading`}
      className="mt-4 rounded-lg border border-yellow-700 p-3"
    >
      <h3
        id={`${prefix}-heading`}
        ref={heading}
        tabIndex={-1}
        className="font-medium text-yellow-200"
      >
        Podobne wpisy w rejestrze
      </h3>
      <div className="mt-3 grid items-start gap-3 sm:grid-cols-2">
        <section
          aria-label="Bieżący dokument"
          className="min-w-0 rounded-lg bg-gray-950 p-3"
        >
          <h4 className="mb-2 text-sm font-medium text-white">
            Bieżący dokument
          </h4>
          <BillComparison
            bill={{
              ...current,
              number: current.number ?? null,
              issue_date: current.issue_date ?? null,
            }}
          />
        </section>
        <ul aria-label="Istniejące wpisy" className="min-w-0 space-y-2">
          {candidates.map((candidate) => {
            const selected = candidate.id === selectedId;
            const detailsId = `${prefix}-${candidate.id}`;
            return (
              <li
                key={candidate.id}
                className={`rounded-lg border bg-gray-950 p-3 ${selected ? "border-yellow-500" : "border-gray-800"}`}
              >
                <div id={detailsId}>
                  <BillComparison
                    bill={selected && attachTarget ? attachTarget : candidate}
                  />
                </div>
                <button
                  type="button"
                  className="btn-secondary mt-2"
                  aria-describedby={detailsId}
                  aria-pressed={selected}
                  onClick={() => onAttach(candidate)}
                  disabled={disabled || (selected && attachTargetLoading)}
                >
                  Dołącz do istniejącego
                </button>
                {selected && attachTargetLoading && (
                  <p role="status" className="mt-2 text-sm text-gray-400">
                    Pobieranie aktualnych danych wpisu…
                  </p>
                )}
                {selected && attachTargetError && (
                  <p role="alert" className="mt-2 text-sm text-red-300">
                    Nie udało się pobrać wpisu. Wybierz go ponownie.
                  </p>
                )}
                {selected &&
                  attachTarget &&
                  !attachTargetLoading &&
                  !attachTargetError &&
                  (canAttach ? (
                    <button
                      type="button"
                      className="btn-primary mt-2"
                      aria-describedby={detailsId}
                      onClick={() => onConfirmAttach(attachTarget)}
                      disabled={disabled}
                    >
                      Potwierdź dołączenie
                    </button>
                  ) : (
                    <p className="mt-2 text-sm text-yellow-200">
                      Ten wpis nie jest już dostępny do dołączenia.
                    </p>
                  ))}
              </li>
            );
          })}
        </ul>
      </div>
      <button
        type="button"
        className="btn-secondary mt-3"
        onClick={onSeparate}
        disabled={disabled}
      >
        Zarejestruj osobno
      </button>
    </section>
  );
}

function BillComparison({ bill }: { bill: BillComparisonFields }) {
  const total = bill.total_minor;
  const amount =
    total != null && bill.currency
      ? `${((total - (total % 100)) / 100).toLocaleString("pl-PL")},${String(total % 100).padStart(2, "0")} ${bill.currency}`
      : "—";
  const details = [
    ["Sprzedawca", bill.supplier_name || "—"],
    ["Numer", bill.number || "—"],
    [
      "Data wystawienia",
      bill.issue_date ? formatCalendarDate(bill.issue_date) : "—",
    ],
    ["Kwota", amount],
  ];
  return (
    <dl className="space-y-1.5 text-sm break-words">
      {details.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-gray-400">{label}</dt>
          <dd className="text-gray-100">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Field({
  label,
  value,
  onChange,
  onBlur,
  inputMode,
  error,
  autoFocus,
  type = "text",
  note,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  inputMode?: "decimal";
  error?: string;
  autoFocus?: boolean;
  type?: string;
  note?: string;
  required?: boolean;
}) {
  const errorId = useId();
  return (
    <label className="block text-sm text-gray-300">
      {label}
      {note && (
        <span className="ml-2 text-xs text-gray-500">Źródło: {note}</span>
      )}
      <input
        aria-label={label}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        required={required}
        type={type}
        inputMode={inputMode}
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        className="input mt-1 w-full"
      />
      {error && (
        <span
          id={errorId}
          role="alert"
          className="mt-1 block text-sm text-red-300"
        >
          {error}
        </span>
      )}
    </label>
  );
}
import { DocumentProcessingInline } from "./DocumentProcessingInline";

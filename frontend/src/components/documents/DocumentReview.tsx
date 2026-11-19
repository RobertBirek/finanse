import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useApproveBill,
  useAttachBillSource,
  useBill,
  usePrepareBill,
  useSerializedIntentKey,
  type BillApprove,
  type DuplicateCandidate,
} from "../../api/bills";
import {
  useDocumentOriginal,
  useDocumentPreview,
  useDocumentReview,
  usePrepareDocumentReview,
  usePrepareDocumentVision,
  useRetryDocumentOcr,
  useDocumentMetadata,
  useRestoreDocument,
  documentArchiveError,
} from "../../api/documents";
import { useAccounts, useCategories, type Category } from "../../api/finance";
import { categoryOptions } from "../../lib/categories";
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
const minor = (raw: string) =>
  /^\d+(\.\d{1,2})?$/.test(raw) ? Math.round(Number(raw) * 100) : null;
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
  const [attachComparison, setAttachComparison] = useState<{
    id: string;
    version: number;
  } | null>(null);
  const currentDraft = useBill(draftBill?.id ?? null, false);
  const categories = useCategories();
  const accounts = useAccounts();
  const { form, update, applyNewSuggestions } = useReviewForm(
    documentId,
    metadata.isLoading ? undefined : review.data,
    categories.data,
  );
  const formKey = JSON.stringify(form);
  const matchingDuplicates =
    duplicateReview?.formKey === formKey ? duplicateReview : null;
  const [conflict, setConflict] = useState<"draft" | "attach" | null>(null);
  const [refreshedConflict, setRefreshedConflict] = useState<
    "draft" | "attach" | null
  >(null);
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
    if (approvalPending || conflict || matchingDuplicates) return;
    const total_minor = minor(form.total);
    if (
      total_minor === null ||
      !form.supplier_name.trim() ||
      !form.description.trim() ||
      !form.currency
    )
      return;
    const fields: ApprovalFields = {
      kind: form.kind,
      supplier_name: form.supplier_name.trim(),
      description: form.description.trim(),
      total_minor,
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
                  onClick={async () => {
                    const result =
                      conflict === "draft"
                        ? await currentDraft.refetch()
                        : await attachTarget.refetch();
                    if (result.data) {
                      setRefreshedConflict(conflict);
                      if (conflict === "draft" && draftBill)
                        setDraftBill({
                          ...draftBill,
                          version: result.data.version,
                        });
                      if (conflict === "attach")
                        setAttachComparison({
                          id: result.data.id,
                          version: result.data.version,
                        });
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
            </div>
          ) : null}
          {review.isError || !review.data ? (
            <>
              <button
                type="button"
                className="btn-primary"
                disabled={!canProcess}
                onClick={() => {
                  setShowLatest(true);
                  prepare.mutate({ documentId, refresh: false });
                }}
              >
                Sprawdź dane
              </button>
              {needsPdfOcr && retryLocalOcr}
            </>
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
              {unsupported ? (
                <p role="alert" className="mt-3 text-sm text-yellow-300">
                  Ten dokument zawiera wiele pozycji albo nie jest
                  fakturą/paragonem. Nie trafia do rejestru finansowego jako
                  jedna pozycja.
                </p>
              ) : (
                <ReviewForm
                  form={form}
                  update={update}
                  provenance={review.data.provenance}
                  onSubmit={submit}
                  pending={approvalPending}
                  submitBlocked={!!conflict || !!matchingDuplicates}
                  categories={categories.data ?? []}
                  accounts={accounts.data ?? []}
                />
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
              {draftBill && matchingDuplicates && (
                <DuplicateChoices
                  candidates={matchingDuplicates.candidates}
                  onAttach={(candidate) => {
                    setAttachComparison(null);
                    setAttachTargetId(candidate.id);
                  }}
                  attachTarget={attachComparison ?? attachTarget.data}
                  attachTargetLoading={attachTarget.isLoading}
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
                  disabled={!!conflict || approvalPending}
                />
              )}
            </>
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
  submitBlocked,
  categories,
  accounts,
}: {
  form: ReviewForm;
  update: (key: keyof ReviewForm, value: string) => void;
  provenance: Record<string, string>;
  onSubmit: () => void;
  pending: boolean;
  submitBlocked: boolean;
  categories: Category[];
  accounts: { id: string; name: string; is_active: boolean }[];
}) {
  return (
    <form
      className="mt-4"
      aria-busy={pending}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <fieldset disabled={pending} className="min-w-0 space-y-3">
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
        <p className="text-xs text-gray-400">
          Sugestia AI nie jest zatwierdzoną kategorią. Możesz ją zmienić lub
          wyczyścić.
        </p>
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
  onAttach,
  attachTarget,
  attachTargetLoading,
  onConfirmAttach,
  onSeparate,
  disabled,
}: {
  candidates: DuplicateCandidate[];
  onAttach: (candidate: DuplicateCandidate) => void;
  attachTarget?: { id: string; version: number };
  attachTargetLoading: boolean;
  onConfirmAttach: (target: { id: string; version: number }) => void;
  onSeparate: () => void;
  disabled: boolean;
}) {
  return (
    <div className="mt-3 rounded-lg border border-yellow-700 p-3">
      <p role="status" className="text-sm text-yellow-200">
        Znaleziono podobny dokument. Wybierz świadomie: dołącz źródło albo
        zarejestruj osobno.
      </p>
      {candidates.map((candidate) => (
        <button
          key={candidate.id}
          type="button"
          className="btn-secondary mt-2 mr-2"
          onClick={() => onAttach(candidate)}
          disabled={disabled}
        >
          Dołącz do istniejącego
        </button>
      ))}
      {attachTargetLoading && (
        <span role="status" className="ml-2 text-sm text-gray-400">
          Pobieranie wersji rejestru…
        </span>
      )}
      {attachTarget && (
        <button
          type="button"
          className="btn-secondary mt-2 mr-2"
          onClick={() => onConfirmAttach(attachTarget)}
          disabled={disabled}
        >
          Potwierdź dołączenie
        </button>
      )}
      <button
        type="button"
        className="btn-primary mt-2"
        onClick={onSeparate}
        disabled={disabled}
      >
        Zarejestruj osobno
      </button>
    </div>
  );
}
function Field({
  label,
  value,
  onChange,
  type = "text",
  note,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  note?: string;
  required?: boolean;
}) {
  return (
    <label className="block text-sm text-gray-300">
      {label}
      {note && (
        <span className="ml-2 text-xs text-gray-500">Źródło: {note}</span>
      )}
      <input
        aria-label={label}
        required={required}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input mt-1 w-full"
      />
    </label>
  );
}
import { DocumentProcessingInline } from "./DocumentProcessingInline";

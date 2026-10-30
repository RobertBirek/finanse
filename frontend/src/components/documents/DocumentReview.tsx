import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useApproveBill,
  useAttachBillSource,
  useBill,
  useDuplicateCandidates,
  usePrepareBill,
  useSerializedIntentKey,
  type BillApprove,
} from "../../api/bills";
import {
  useDocumentOriginal,
  useDocumentPreview,
  useDocumentReview,
  usePrepareDocumentReview,
  useRetryDocumentOcr,
} from "../../api/documents";
import { useAccounts, useCategories } from "../../api/finance";
import { Dialog } from "../Dialog";
import type { AxiosError } from "axios";

type Props = { documentId: string; onClose: () => void };
type Form = {
  kind: "invoice" | "receipt";
  supplier_name: string;
  description: string;
  total: string;
  currency: "PLN" | "EUR" | "USD";
  issue_date: string;
  sale_date: string;
  due_date: string;
  number: string;
  supplier_tax_id: string;
  payee_iban: string;
  category_id: string;
  payment_account_id: string;
};
const empty: Form = {
  kind: "invoice",
  supplier_name: "",
  description: "",
  total: "",
  currency: "PLN",
  issue_date: "",
  sale_date: "",
  due_date: "",
  number: "",
  supplier_tax_id: "",
  payee_iban: "",
  category_id: "",
  payment_account_id: "",
};
const minor = (raw: string) =>
  /^\d+(\.\d{1,2})?$/.test(raw) ? Math.round(Number(raw) * 100) : null;
const mutationError = (error: unknown) =>
  (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ??
  "Nie udało się zapisać zmian. Popraw pola i spróbuj ponownie.";

export function DocumentReview({ documentId, onClose }: Props) {
  const navigate = useNavigate();
  const review = useDocumentReview(documentId);
  const preview = useDocumentPreview(documentId);
  const original = useDocumentOriginal(documentId);
  const prepare = usePrepareDocumentReview();
  const retryOcr = useRetryDocumentOcr();
  const prepareBill = usePrepareBill();
  const approve = useApproveBill();
  const attach = useAttachBillSource();
  const keyFor = useSerializedIntentKey();
  const [draftBill, setDraftBill] = useState<{
    id: string;
    version: number;
  } | null>(null);
  const [attachTargetId, setAttachTargetId] = useState<string | null>(null);
  const duplicates = useDuplicateCandidates(draftBill?.id ?? null);
  const attachTarget = useBill(attachTargetId);
  const currentDraft = useBill(draftBill?.id ?? null, false);
  const categories = useCategories();
  const accounts = useAccounts();
  const [form, setForm] = useState<Form>(empty);
  const [conflict, setConflict] = useState<"draft" | "attach" | null>(null);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
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
  useEffect(() => {
    const fields = review.data?.fields;
    if (!fields) return;
    setForm({
      kind: review.data?.document_type === "receipt" ? "receipt" : "invoice",
      supplier_name: fields.supplier_name ?? "",
      description: fields.description ?? "",
      total: fields.total ?? "",
      currency: fields.currency ?? "PLN",
      issue_date: fields.issue_date ?? "",
      sale_date: fields.sale_date ?? "",
      due_date: fields.due_date ?? "",
      number: fields.number ?? "",
      supplier_tax_id: fields.supplier_tax_id ?? "",
      payee_iban: fields.payee_iban ?? "",
      category_id: "",
      payment_account_id: "",
    });
  }, [review.data]);
  const unsupported =
    review.data?.document_type === "multiple" ||
    review.data?.document_type === "unsupported" ||
    review.data?.document_type === "statement" ||
    review.data?.document_type === "loan_schedule" ||
    review.data?.document_type === "other";
  const update = (key: keyof Form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const submit = () => {
    const total_minor = minor(form.total);
    if (
      total_minor === null ||
      !form.supplier_name.trim() ||
      !form.description.trim()
    )
      return;
    prepareBill.mutate(
      { documentId },
      {
        onSuccess: (bill) =>
          setDraftBill({ id: bill.id, version: bill.version }),
      },
    );
  };
  const approveDraft = (separate: boolean) => {
    if (!draftBill || conflict) return;
    const total_minor = minor(form.total);
    if (total_minor === null) return;
    const data: BillApprove = {
      version: draftBill.version,
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
      ...(separate ? { duplicate_decision: "separate" as const } : {}),
    };
    approve.mutate(
      {
        billId: draftBill.id,
        data,
        idempotencyKey: keyFor({
          action: "approve-bill",
          billId: draftBill.id,
          data,
        }),
      },
      {
        onSuccess: (bill) => navigate(`/finances/documents?bill=${bill.id}`),
        onError: (error) => {
          if ((error as AxiosError).response?.status === 409)
            setConflict("draft");
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
        prepareBill.isPending ||
        approve.isPending ||
        attach.isPending
      }
    >
      <div className="flex items-center justify-between gap-3 border-b border-gray-800 p-4">
        <h2 className="text-lg font-semibold text-white">Sprawdź dane</h2>
        <button type="button" onClick={onClose} className="btn-secondary">
          Zamknij
        </button>
      </div>
      <div className="grid gap-5 p-4 md:grid-cols-2">
        <section>
          <h3 className="font-medium text-white">Oryginał dokumentu</h3>
          {originalUrl && (
            <a
              href={originalUrl}
              download="dokument"
              className="mt-2 inline-block text-sm text-advisor-400 hover:underline"
            >
              Pobierz autoryzowany oryginał
            </a>
          )}
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
          ) : (
            <p className="mt-3 text-sm text-gray-400">
              Podgląd jest ładowany z prywatnego źródła.
            </p>
          )}
        </section>
        <section>
          {prepare.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              Nie udało się przygotować przeglądu dokumentu. Spróbuj ponownie.
            </p>
          ) : null}
          {retryOcr.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              Nie udało się ponowić OCR. Możesz poprawić pola ręcznie.
            </p>
          ) : null}
          {prepareBill.error || approve.error || attach.error ? (
            <p role="alert" className="mb-3 text-sm text-red-300">
              {mutationError(
                prepareBill.error || approve.error || attach.error,
              )}
              {(approve.error as AxiosError | null)?.response?.status === 409 ||
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
              {currentVersion != null
                ? ` Aktualna wersja: ${currentVersion}.`
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
                      setCurrentVersion(result.data.version);
                      if (conflict === "draft" && draftBill)
                        setDraftBill({
                          ...draftBill,
                          version: result.data.version,
                        });
                    }
                  }}
                >
                  Odśwież aktualny dokument
                </button>
                {currentVersion != null ? (
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
            <button
              type="button"
              className="btn-primary"
              onClick={() => prepare.mutate({ documentId, refresh: false })}
            >
              Sprawdź dane
            </button>
          ) : (
            <>
              <p className="text-sm text-gray-400">
                OCR i zewnętrzny dostawca językowy mogą się pomylić. Porównaj
                dane z oryginałem i popraw je ręcznie.
              </p>
              {review.data.status === "error" && (
                <p role="alert" className="mt-3 text-sm text-red-300">
                  Nie udało się uzyskać propozycji od zewnętrznego dostawcy.
                  Możesz uzupełnić pola ręcznie.
                  <button
                    type="button"
                    className="btn-secondary ml-2"
                    onClick={() => retryOcr.mutate({ documentId })}
                  >
                    Ponów OCR
                  </button>
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
                  pending={prepareBill.isPending || approve.isPending}
                  categories={categories.data ?? []}
                  accounts={accounts.data ?? []}
                />
              )}
              {draftBill && (
                <DuplicateChoices
                  candidates={duplicates.data ?? []}
                  loading={duplicates.isLoading}
                  onAttach={(candidate) => setAttachTargetId(candidate.id)}
                  attachTarget={attachTarget.data}
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
                          if ((error as AxiosError).response?.status === 409)
                            setConflict("attach");
                        },
                      },
                    )
                  }
                  onSeparate={() => approveDraft(true)}
                  onApprove={() => approveDraft(false)}
                  disabled={!!conflict}
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
  categories,
  accounts,
}: {
  form: Form;
  update: (key: keyof Form, value: string) => void;
  provenance: Record<string, string>;
  onSubmit: () => void;
  pending: boolean;
  categories: { id: string; name: string; type: string; is_active: boolean }[];
  accounts: { id: string; name: string; is_active: boolean }[];
}) {
  return (
    <form
      className="mt-4 space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
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
          {categories
            .filter((item) => item.is_active && item.type === "expense")
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
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
        Kategoria i konto płatności są opcjonalne i wybierzesz je w rejestrze.
      </p>
      <button type="submit" disabled={pending} className="btn-primary">
        Zatwierdź do rejestru
      </button>
    </form>
  );
}

function DuplicateChoices({
  candidates,
  loading,
  onAttach,
  attachTarget,
  attachTargetLoading,
  onConfirmAttach,
  onSeparate,
  onApprove,
  disabled,
}: {
  candidates: { id: string; reasons: string[] }[];
  loading: boolean;
  onAttach: (candidate: { id: string; reasons: string[] }) => void;
  attachTarget?: { id: string; version: number };
  attachTargetLoading: boolean;
  onConfirmAttach: (target: { id: string; version: number }) => void;
  onSeparate: () => void;
  onApprove: () => void;
  disabled: boolean;
}) {
  if (loading)
    return (
      <p role="status" className="mt-3 text-sm text-gray-400">
        Sprawdzanie podobnych dokumentów…
      </p>
    );
  if (!candidates.length)
    return (
      <button
        type="button"
        className="btn-primary mt-3"
        onClick={onApprove}
        disabled={disabled}
      >
        Zatwierdź do rejestru
      </button>
    );
  return (
    <div className="mt-3 rounded-lg border border-yellow-700 p-3">
      <p className="text-sm text-yellow-200">
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

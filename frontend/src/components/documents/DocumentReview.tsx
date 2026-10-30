import { useEffect, useMemo, useState } from "react";
import {
  useApproveBill,
  usePrepareBill,
  type BillApprove,
} from "../../api/bills";
import {
  useDocumentOriginal,
  useDocumentPreview,
  useDocumentReview,
  usePrepareDocumentReview,
} from "../../api/documents";
import { Dialog } from "../Dialog";

type Props = { documentId: string; onClose: () => void };
type Form = {
  kind: "invoice" | "receipt";
  supplier_name: string;
  description: string;
  total: string;
  currency: "PLN" | "EUR" | "USD";
  issue_date: string;
  due_date: string;
  number: string;
  supplier_tax_id: string;
  payee_iban: string;
};
const empty: Form = {
  kind: "invoice",
  supplier_name: "",
  description: "",
  total: "",
  currency: "PLN",
  issue_date: "",
  due_date: "",
  number: "",
  supplier_tax_id: "",
  payee_iban: "",
};
const minor = (raw: string) =>
  /^\d+(\.\d{1,2})?$/.test(raw) ? Math.round(Number(raw) * 100) : null;

export function DocumentReview({ documentId, onClose }: Props) {
  const review = useDocumentReview(documentId);
  const preview = useDocumentPreview(documentId);
  const original = useDocumentOriginal(documentId);
  const prepare = usePrepareDocumentReview();
  const prepareBill = usePrepareBill();
  const approve = useApproveBill();
  const [form, setForm] = useState<Form>(empty);
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
      due_date: fields.due_date ?? "",
      number: fields.number ?? "",
      supplier_tax_id: fields.supplier_tax_id ?? "",
      payee_iban: fields.payee_iban ?? "",
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
        onSuccess: (bill) => {
          const data: BillApprove = {
            version: bill.version,
            kind: form.kind,
            supplier_name: form.supplier_name.trim(),
            description: form.description.trim(),
            total_minor,
            currency: form.currency,
            declaration: form.kind === "receipt" ? "declared_paid" : "unknown",
            supplier_tax_id: form.supplier_tax_id || null,
            number: form.number || null,
            issue_date: form.issue_date || null,
            due_date: form.due_date || null,
            payee_iban: form.payee_iban || null,
          };
          approve.mutate({ billId: bill.id, data });
        },
      },
    );
  };
  return (
    <Dialog
      label="Sprawdź dane dokumentu"
      onClose={onClose}
      panelClassName="w-full max-w-4xl rounded-xl border border-gray-700 bg-gray-900"
      busy={prepare.isPending || prepareBill.isPending || approve.isPending}
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
}: {
  form: Form;
  update: (key: keyof Form, value: string) => void;
  provenance: Record<string, string>;
  onSubmit: () => void;
  pending: boolean;
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
        label="Opis"
        value={form.description}
        onChange={(v) => update("description", v)}
        required
      />
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

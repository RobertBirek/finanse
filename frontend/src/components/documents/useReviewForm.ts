import { useEffect, useRef, useState } from "react";
import type { DocumentReview } from "../../api/documents";
import type { Category } from "../../api/finance";

export type ReviewForm = {
  kind: "invoice" | "receipt";
  supplier_name: string;
  description: string;
  total: string;
  currency: "" | "PLN" | "EUR" | "USD";
  issue_date: string;
  sale_date: string;
  due_date: string;
  number: string;
  supplier_tax_id: string;
  payee_iban: string;
  category_id: string;
  payment_account_id: string;
};

export const emptyReviewForm: ReviewForm = {
  kind: "invoice",
  supplier_name: "",
  description: "",
  total: "",
  currency: "",
  issue_date: "",
  sale_date: "",
  due_date: "",
  number: "",
  supplier_tax_id: "",
  payee_iban: "",
  category_id: "",
  payment_account_id: "",
};

type ReviewInput = Pick<
  DocumentReview,
  "id" | "revision" | "status" | "document_type"
> & {
  fields: Partial<DocumentReview["fields"]>;
  suggested_category_id?: string | null;
};
type SuggestedField = Exclude<
  keyof ReviewForm,
  "category_id" | "payment_account_id"
>;
const reviewKeys: SuggestedField[] = [
  "kind",
  "supplier_name",
  "description",
  "total",
  "currency",
  "issue_date",
  "sale_date",
  "due_date",
  "number",
  "supplier_tax_id",
  "payee_iban",
];

function suggestion(review: ReviewInput): Pick<ReviewForm, SuggestedField> {
  const fields = review.fields;
  return {
    kind: review.document_type === "receipt" ? "receipt" : "invoice",
    supplier_name: fields.supplier_name ?? "",
    description: fields.description ?? "",
    total: fields.total ?? "",
    currency: fields.currency ?? "",
    issue_date: fields.issue_date ?? "",
    sale_date: fields.sale_date ?? "",
    due_date: fields.due_date ?? "",
    number: fields.number ?? "",
    supplier_tax_id: fields.supplier_tax_id ?? "",
    payee_iban: fields.payee_iban ?? "",
  };
}

const noCategories: Category[] = [];
export function useReviewForm(
  documentId: string,
  review?: ReviewInput,
  categories: Category[] = noCategories,
  requestedCategoryId?: string | null,
) {
  const [form, setForm] = useState<ReviewForm>(emptyReviewForm);
  const context = useRef(documentId);
  const dirty = useRef(new Set<keyof ReviewForm>());
  const applied = useRef(new Set<string>());
  useEffect(() => {
    if (context.current !== documentId) {
      context.current = documentId;
      dirty.current.clear();
      applied.current.clear();
      setForm(emptyReviewForm);
    }
  }, [documentId]);
  useEffect(() => {
    if (
      !review ||
      context.current !== documentId ||
      review.status === "pending" ||
      review.status === "processing" ||
      applied.current.has(review.id)
    )
      return;
    const next = suggestion(review);
    setForm((current) => {
      const updated = { ...current } as ReviewForm;
      for (const key of reviewKeys)
        if (!dirty.current.has(key))
          (updated as Record<string, string>)[key] = next[key];
      return updated;
    });
    applied.current.add(review.id);
  }, [documentId, review]);
  const eligibleCategory =
    categories.find(
      (category) =>
        category.id ===
          (requestedCategoryId ?? review?.suggested_category_id) &&
        category.is_active &&
        category.type === "expense",
    )?.id ?? "";
  useEffect(() => {
    if (
      !review ||
      review.status === "pending" ||
      review.status === "processing" ||
      context.current !== documentId ||
      dirty.current.has("category_id")
    )
      return;
    setForm((current) =>
      current.category_id === eligibleCategory
        ? current
        : { ...current, category_id: eligibleCategory },
    );
  }, [documentId, review, eligibleCategory]);
  const update = (key: keyof ReviewForm, value: string) => {
    dirty.current.add(key);
    setForm((current) => ({ ...current, [key]: value }) as ReviewForm);
  };
  const applyNewSuggestions = () => {
    if (!review) return;
    const next = suggestion(review);
    setForm((current) => ({
      ...current,
      ...next,
      category_id: current.category_id,
      payment_account_id: current.payment_account_id,
    }));
  };
  return { form, update, isDirty: dirty.current.size > 0, applyNewSuggestions };
}

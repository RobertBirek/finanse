import type { ReceiptBody, ReceiptHistoryRef } from "../../../api/receiptItems";
import { parsePlnToGrosze } from "../../../api/finance";
export interface DraftLine {
  line_key: string;
  name: string;
  amount: string;
  category_id: string | null;
  hint: ReceiptHistoryRef | null;
}
export interface DraftDiscount {
  discount_key: string;
  name: string;
  amount: string;
  shares: Record<string, string>;
}
export interface ReceiptDraft {
  store_id: string | null;
  store_version: number | null;
  lines: DraftLine[];
  discounts: DraftDiscount[];
}
export function minorInput(value: number | null) {
  if (value === null) return "";
  const digits = String(value).padStart(3, "0");
  return `${digits.slice(0, -2)},${digits.slice(-2)}`;
}
export function fromReceiptBody(body: ReceiptBody): ReceiptDraft {
  return {
    store_id: body.store_id,
    store_version: body.store_version,
    lines: body.lines.map((l) => ({
      ...l,
      amount: minorInput(l.amount_minor),
    })),
    discounts: body.discounts.map((d) => ({
      discount_key: d.discount_key,
      name: d.name,
      amount: minorInput(d.amount_minor),
      shares: Object.fromEntries(
        d.shares.map((s) => [s.line_key, minorInput(s.amount_minor)]),
      ),
    })),
  };
}
function amount(raw: string, zero = false) {
  if (!raw.trim()) return null;
  const n = parsePlnToGrosze(raw, zero);
  if (n === null)
    throw new Error(
      "Popraw kwotę: maksymalnie dwa miejsca po przecinku, bez znaków ujemnych.",
    );
  return n;
}
export function toReceiptBody(draft: ReceiptDraft): ReceiptBody {
  return {
    store_id: draft.store_id,
    store_version: draft.store_version,
    lines: draft.lines.map((l) => ({
      line_key: l.line_key,
      name: l.name,
      amount_minor: amount(l.amount, true),
      category_id: l.category_id,
      hint: l.hint,
    })),
    discounts: draft.discounts.map((d) => ({
      discount_key: d.discount_key,
      name: d.name,
      amount_minor: amount(d.amount),
      shares: Object.entries(d.shares)
        .filter(([, v]) => v.trim())
        .map(([line_key, v]) => ({ line_key, amount_minor: amount(v) })),
    })),
  };
}

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { invalidateFinanceLedger } from "./finance";
import type { CategoryPart, CategorizationContext } from "./categorization";
import type { ReceiptReadEvidence } from "./receiptRead";

export interface ReceiptHistoryRef {
  source_bill_id: string;
  source_revision_id: string;
  source_line_key: string;
  category_id: string;
  match_kind: "exact" | "prefix";
  algorithm_version: string;
  source_sha256: string;
}
export interface ReceiptLine {
  line_key: string;
  name: string;
  amount_minor: number | null;
  category_id: string | null;
  hint: ReceiptHistoryRef | null;
}
export interface ReceiptDiscount {
  discount_key: string;
  name: string;
  amount_minor: number | null;
  shares: { line_key: string; amount_minor: number | null }[];
}
export interface ReceiptBody {
  store_id: string | null;
  store_version: number | null;
  lines: ReceiptLine[];
  discounts: ReceiptDiscount[];
}
export interface ReceiptProblem {
  code: string;
  line_key?: string | null;
  discount_key?: string | null;
  message: string;
}
export interface ReceiptCalculation {
  line_nets: { line_key: string; net_minor: number | null }[];
  net_total_minor: number | null;
  difference_minor: number | null;
  parts: CategoryPart[];
  problems: ReceiptProblem[];
}
export interface ReceiptRevisionView {
  id: string;
  sequence: number;
  kind: "draft" | "approved";
  header_sha256: string;
  body_sha256: string;
  body: ReceiptBody;
  created_at: string;
  current: boolean;
  problems: ReceiptProblem[];
  evidence?: ReceiptReadEvidence | null;
}
export interface ReceiptItemsContext {
  bill_id: string;
  bill_version: number;
  state_version: number;
  editable: boolean;
  blocked_reason: string | null;
  draft: ReceiptRevisionView | null;
  approved: ReceiptRevisionView | null;
  calculation: ReceiptCalculation | null;
  eligible_category_ids: string[];
  limits: {
    max_lines: number;
    max_discounts: number;
    max_discount_shares: number;
    item_name_max_chars: number;
    store_name_max_chars: number;
    history_page_size: number;
    history_prefix_min_chars: number;
  };
}
export interface ReceiptStore {
  id: string;
  name: string;
  active: boolean;
  version: number;
}
export interface ReceiptStorePage {
  items: ReceiptStore[];
  next_cursor: string | null;
}
export interface ReceiptHistoryHint {
  ref: ReceiptHistoryRef;
  product_name: string;
  category_path: string;
  purchased_on: string | null;
  approved_at: string;
}
export interface ReceiptHistoryPage {
  items: ReceiptHistoryHint[];
  match_kind: "exact" | "prefix" | "none";
  conflict: boolean;
  has_more: boolean;
  history_incomplete: boolean;
}
export interface ReceiptPaymentPreview {
  expected_state_version: number;
  approved_revision_id: string;
  transaction_id: string;
  context_snapshot: string;
  preview_snapshot: string;
  before_parts: CategoryPart[];
  after_parts: CategoryPart[];
  target_paths: Record<string, string>;
  line_nets: { line_key: string; net_minor: number | null }[];
  body_sha256: string;
  total_minor: number;
  currency: "PLN";
  notice: string;
}
export interface ReceiptPaymentContext {
  allowed: boolean;
  blocked_reason: string | null;
  last_application: {
    receipt_id: string;
    revision_id: string;
    transaction_id: string;
    items_changed: boolean;
    ledger_changed: boolean;
  } | null;
}
export interface ReceiptPaymentResult {
  context: CategorizationContext;
  state_version: number;
  receipt_id: string;
  revision_id: string;
  grant: Record<string, unknown>;
}
export interface ReceiptCommandInput {
  session: number;
  billId: string;
  key: string;
  body: Record<string, unknown>;
}
function fence(session: number) {
  if (session !== useAuthStore.getState().sessionVersion)
    throw new Error("session_changed");
}
const root = "/finance";
export function useReceiptItems(billId: string) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "receipt-items", session, billId],
    retry: false,
    queryFn: async ({ signal }) =>
      (
        await api.get<ReceiptItemsContext>(`${root}/bills/${billId}/items`, {
          signal,
        })
      ).data,
  });
}
export function useReceiptPaymentContext(billId: string) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "receipt-payment", session, billId],
    retry: false,
    queryFn: async ({ signal }) =>
      (
        await api.get<ReceiptPaymentContext>(
          `${root}/bills/${billId}/items/payment`,
          { signal },
        )
      ).data,
  });
}
export function useReceiptStores(
  cursor: string | null = null,
  includeInactive = false,
) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useInfiniteQuery({
    queryKey: ["finance", "receipt-stores", session, cursor, includeInactive],
    retry: false,
    initialPageParam: cursor,
    queryFn: async ({ signal, pageParam }) =>
      (
        await api.get<ReceiptStorePage>(`${root}/receipt-stores`, {
          signal,
          params: {
            cursor: pageParam ?? undefined,
            include_inactive: includeInactive,
          },
        })
      ).data,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}
export function useReceiptHistory() {
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      session: number;
      billId: string;
      storeId: string;
      name: string;
      signal?: AbortSignal;
    }) => {
      fence(input.session);
      return (
        await api.get<ReceiptHistoryPage>(
          `${root}/bills/${input.billId}/items/history`,
          {
            signal: input.signal,
            params: { store_id: input.storeId, name: input.name },
          },
        )
      ).data;
    },
  });
}
function useReceiptCommand<T>(action: string, ledger = false) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationKey: ["finance", "receipt-items", "write"],
    mutationFn: async (input: ReceiptCommandInput) => {
      fence(input.session);
      return (
        await api.post<T>(
          `${root}/bills/${input.billId}/items/${action}`,
          input.body,
          { headers: { "Idempotency-Key": input.key } },
        )
      ).data;
    },
    onSettled: (_data, _error, input) => {
      if (input.session !== useAuthStore.getState().sessionVersion) return;
      client.invalidateQueries({ queryKey: ["finance", "receipt-items"] });
      client.invalidateQueries({ queryKey: ["finance", "receipt-payment"] });
      client.invalidateQueries({
        queryKey: ["finance", "receipt-read", input.session, input.billId],
      });
      if (ledger) {
        invalidateFinanceLedger(client);
        client.invalidateQueries({ queryKey: ["finance", "bills"] });
        client.invalidateQueries({ queryKey: ["finance", "categorization"] });
        client.invalidateQueries({ queryKey: ["finance", "proposals"] });
      }
    },
  });
}
export function useSaveReceiptDraft() {
  return useReceiptCommand<ReceiptItemsContext>("draft");
}
export function useDiscardReceiptDraft() {
  return useReceiptCommand<ReceiptItemsContext>("discard-draft");
}
export function useApproveReceiptItems() {
  return useReceiptCommand<ReceiptItemsContext>("approve");
}
export function useApplyReceiptPayment() {
  return useReceiptCommand<ReceiptPaymentResult>("payment-apply", true);
}
export function usePreviewReceiptPayment() {
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      session: number;
      billId: string;
      body: { expected_state_version: number; approved_revision_id: string };
    }) => {
      fence(input.session);
      return (
        await api.post<ReceiptPaymentPreview>(
          `${root}/bills/${input.billId}/items/payment-preview`,
          input.body,
        )
      ).data;
    },
  });
}
function useStoreCommand<T>(method: "post" | "patch" | "delete") {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      session: number;
      key: string;
      storeId?: string;
      body: Record<string, unknown>;
    }) => {
      fence(input.session);
      if (method !== "post" && !input.storeId)
        throw new Error("store_required");
      return (
        await api.request<T>({
          method,
          url: `${root}/receipt-stores${method === "post" ? "" : `/${input.storeId}`}`,
          data: input.body,
          headers: { "Idempotency-Key": input.key },
        })
      ).data;
    },
    onSettled: (_data, _error, input) => {
      if (input.session === useAuthStore.getState().sessionVersion) {
        client.invalidateQueries({ queryKey: ["finance", "receipt-stores"] });
        client.invalidateQueries({ queryKey: ["finance", "receipt-items"] });
        client.invalidateQueries({ queryKey: ["finance", "receipt-payment"] });
      }
    },
  });
}
export function useCreateReceiptStore() {
  return useStoreCommand<ReceiptStore>("post");
}
export function useChangeReceiptStore() {
  return useStoreCommand<ReceiptStore>("patch");
}
export function useDeleteReceiptStore() {
  return useStoreCommand<{ id: string; deleted: boolean }>("delete");
}

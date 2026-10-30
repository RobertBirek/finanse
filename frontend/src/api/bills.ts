import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import api from "../lib/api";

export type BillKind = "invoice" | "receipt";
export type PaymentDeclaration = "unknown" | "payable" | "declared_paid";
export type BillResponse = {
  id: string;
  kind: BillKind | null;
  supplier_name: string | null;
  supplier_tax_id: string | null;
  number: string | null;
  issue_date: string | null;
  sale_date: string | null;
  due_date: string | null;
  payee_iban: string | null;
  description: string | null;
  category_id: string | null;
  payment_account_id: string | null;
  total_minor: number | null;
  currency: "PLN" | "EUR" | "USD" | null;
  declaration: PaymentDeclaration;
  lifecycle: "active" | "archived" | "cancelled";
  review: "draft" | "approved" | "rejected";
  version: number;
  paid_minor: number;
  remaining_minor: number;
  reconciliation: "none" | "partial" | "full";
  sources: { document_id: string }[];
  allocations: { id: string; posting_id: string; amount_minor: number }[];
  extraction_revision_id: string | null;
  coverage: {
    scheduled_item_id: string;
    occurrence_date: string;
    choice: "replace" | "separate";
    source_lifecycle: "active" | "archived" | "cancelled";
  } | null;
  recurring_decision: "separate" | null;
  forecast_exclusion_reasons: string[];
};
export type BillPage = {
  items: BillResponse[];
  total: number;
  limit: number;
  offset: number;
};
export type BillFilters = {
  kind?: BillKind;
  review?: BillResponse["review"];
  declaration?: PaymentDeclaration;
  lifecycle?: BillResponse["lifecycle"];
  due_from?: string;
  due_to?: string;
  query?: string;
  limit?: number;
  offset?: number;
};
export type BillCandidate = {
  transaction_id: string;
  posting_id: string;
  date: string;
  account: string;
  amount_minor: number;
  unallocated_minor: number;
  reasons: string[];
  legacy_inbox_reference: string | null;
  recurring_conflicts: string[];
  recurring_forecast_before_pln: number | null;
  recurring_forecast_after_pln: number | null;
};
export type BillCandidatePage = {
  items: BillCandidate[];
  total: number;
  limit: number;
  offset: number;
};
export type CoverageCandidate = {
  scheduled_item_id: string;
  occurrence_date: string;
  name: string;
  estimate_amount_pln: number | null;
};
export type BillApprove = {
  version: number;
  kind: BillKind;
  supplier_name: string;
  supplier_tax_id?: string | null;
  number?: string | null;
  issue_date?: string | null;
  sale_date?: string | null;
  due_date?: string | null;
  payee_iban?: string | null;
  category_id?: string | null;
  payment_account_id?: string | null;
  description: string;
  total_minor: number;
  currency: "PLN" | "EUR" | "USD";
  declaration?: PaymentDeclaration;
  duplicate_decision?: "separate";
};
export type DuplicateCandidate = { id: string; reasons: string[] };
const headers = () => ({ "Idempotency-Key": crypto.randomUUID() });
export const stableKey = () => crypto.randomUUID();
/** Reuse a key only for an identical user decision; changed payloads are new intents. */
export function useSerializedIntentKey() {
  const current = useRef<{ key: string; serialized: string } | null>(null);
  return (intent: Record<string, unknown>) => {
    const serialized = JSON.stringify(intent, Object.keys(intent).sort());
    if (current.current?.serialized !== serialized)
      current.current = { serialized, key: stableKey() };
    return current.current.key;
  };
}
const invalidate = (
  client: ReturnType<typeof useQueryClient>,
  ledger = false,
) => {
  client.invalidateQueries({ queryKey: ["finance", "bills"] });
  client.invalidateQueries({ queryKey: ["documents"] });
  client.invalidateQueries({ queryKey: ["finance", "cashflow"] });
  if (ledger) {
    client.invalidateQueries({ queryKey: ["finance", "transactions"] });
    client.invalidateQueries({ queryKey: ["finance", "budget"] });
    client.invalidateQueries({ queryKey: ["finance", "summary"] });
  }
};

export function usePrepareBill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ documentId }: { documentId: string }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/prepare/${documentId}`,
          undefined,
          { headers: headers() },
        )
      ).data,
    onSuccess: () => invalidate(client),
  });
}
export function useApproveBill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      billId,
      data,
      idempotencyKey,
    }: {
      billId: string;
      data: BillApprove;
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(`/finance/bills/${billId}/approve`, data, {
          headers: { "Idempotency-Key": idempotencyKey },
        })
      ).data,
    onSuccess: () => invalidate(client),
  });
}
export function useAttachBillSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      billId,
      documentId,
      expectedVersion,
      idempotencyKey,
    }: {
      billId: string;
      documentId: string;
      expectedVersion: number;
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/sources/${documentId}`,
          undefined,
          {
            params: { expected_version: expectedVersion },
            headers: { "Idempotency-Key": idempotencyKey },
          },
        )
      ).data,
    onSuccess: () => invalidate(client),
  });
}
export function useDuplicateCandidates(billId: string | null) {
  return useQuery({
    queryKey: ["finance", "bills", billId, "duplicates"],
    enabled: !!billId,
    queryFn: async () =>
      (
        await api.get<DuplicateCandidate[]>(
          `/finance/bills/${billId}/duplicates`,
        )
      ).data,
  });
}
export function useBill(billId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["finance", "bills", billId],
    enabled: !!billId && enabled,
    queryFn: async () =>
      (await api.get<BillResponse>(`/finance/bills/${billId}`)).data,
  });
}

export function useBills(filters: BillFilters = {}) {
  return useQuery({
    queryKey: ["finance", "bills", filters],
    queryFn: async () =>
      (await api.get<BillPage>("/finance/bills", { params: filters })).data,
  });
}
export function useBillCandidates(
  billId: string | null,
  filters: {
    limit?: number;
    offset?: number;
    query?: string;
    date_from?: string;
    date_to?: string;
    include_older?: boolean;
  } = {},
) {
  return useQuery({
    queryKey: ["finance", "bills", billId, "candidates", filters],
    enabled: !!billId,
    queryFn: async () =>
      (
        await api.get<BillCandidatePage>(
          `/finance/bills/${billId}/candidates`,
          { params: filters },
        )
      ).data,
  });
}
function useBillMutation<T>(
  mutationFn: (input: T & { idempotencyKey: string }) => Promise<BillResponse>,
  ledger = false,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => invalidate(client, ledger),
  });
}
export function useAllocateBillPayment() {
  return useBillMutation(
    async ({
      billId,
      idempotencyKey,
      ...data
    }: {
      billId: string;
      version: number;
      posting_id: string;
      amount_minor: number;
      confirm_recurring_conflict?: true;
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/allocations`,
          data,
          { headers: { "Idempotency-Key": idempotencyKey } },
        )
      ).data,
  );
}
export function useUnlinkBillPayment() {
  return useBillMutation(
    async ({
      billId,
      allocationId,
      expected_version,
      idempotencyKey,
    }: {
      billId: string;
      allocationId: string;
      expected_version: number;
      idempotencyKey: string;
    }) =>
      (
        await api.delete<BillResponse>(
          `/finance/bills/${billId}/allocations/${allocationId}`,
          {
            params: { expected_version },
            headers: { "Idempotency-Key": idempotencyKey },
          },
        )
      ).data,
  );
}
export function useRecordBillPayment() {
  return useBillMutation(
    async ({
      billId,
      idempotencyKey,
      ...data
    }: {
      billId: string;
      version: number;
      account_id: string;
      category_id: string;
      payment_date: string;
      amount_minor: number;
      description: string;
      confirm_new_payment: true;
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/payments`,
          data,
          { headers: { "Idempotency-Key": idempotencyKey } },
        )
      ).data,
    true,
  );
}
export function useBillCoverage() {
  const client = useQueryClient();
  const decide = useMutation({
    mutationFn: async ({
      billId,
      idempotencyKey,
      ...data
    }: {
      billId: string;
      version: number;
      choice: "replace" | "separate";
      scheduled_item_id?: string;
      occurrence_date?: string;
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/coverage`,
          data,
          { headers: { "Idempotency-Key": idempotencyKey } },
        )
      ).data,
    onSuccess: () => invalidate(client),
  });
  const unlink = useMutation({
    mutationFn: async ({
      billId,
      expected_version,
      idempotencyKey,
    }: {
      billId: string;
      expected_version: number;
      idempotencyKey: string;
    }) =>
      (
        await api.delete<BillResponse>(`/finance/bills/${billId}/coverage`, {
          params: { expected_version, confirm_unlink: true },
          headers: { "Idempotency-Key": idempotencyKey },
        })
      ).data,
    onSuccess: () => invalidate(client),
  });
  return { decide, unlink };
}
export function useUpdateBillLifecycle() {
  return useBillMutation(
    async ({
      billId,
      expected_version,
      lifecycle,
      idempotencyKey,
    }: {
      billId: string;
      expected_version: number;
      lifecycle: BillResponse["lifecycle"];
      idempotencyKey: string;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/lifecycle`,
          { expected_version, lifecycle },
          { headers: { "Idempotency-Key": idempotencyKey } },
        )
      ).data,
  );
}

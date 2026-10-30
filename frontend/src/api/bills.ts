import { useMutation, useQueryClient } from "@tanstack/react-query";
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
  allocations: { posting_id: string; amount_minor: number }[];
  extraction_revision_id: string | null;
  forecast_exclusion_reasons: string[];
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
const headers = () => ({ "Idempotency-Key": crypto.randomUUID() });
const invalidate = (client: ReturnType<typeof useQueryClient>) =>
  client.invalidateQueries({ queryKey: ["finance", "bills"] });

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
    }: {
      billId: string;
      data: BillApprove;
    }) =>
      (
        await api.post<BillResponse>(`/finance/bills/${billId}/approve`, data, {
          headers: headers(),
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
    }: {
      billId: string;
      documentId: string;
      expectedVersion: number;
    }) =>
      (
        await api.post<BillResponse>(
          `/finance/bills/${billId}/sources/${documentId}`,
          undefined,
          { params: { expected_version: expectedVersion }, headers: headers() },
        )
      ).data,
    onSuccess: () => invalidate(client),
  });
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import api from "../lib/api";

export type CardInstallment = {
  number: number;
  due_date: string;
  principal_pln: number;
  interest_pln: number;
  fees_pln: number;
};
export type CardPlan = {
  id: string;
  name: string;
  source_transaction_id: string;
  principal_pln: number;
  apr: string;
  fees_pln: number;
  version: number;
  schedule_kind: "estimated" | "bank";
  remaining_principal_pln: number;
  status: "active" | "closed";
  installments: CardInstallment[];
};
export type CardStatement = {
  id: string;
  period_start: string;
  period_end: string;
  due_date: string;
  debt_pln: number;
  minimum_pln: number;
  remaining_pln: number;
  minimum_remaining_pln: number;
  reconciliation_difference_pln: number;
  source_reference: string;
};
export type CardCharge = {
  id: string;
  transaction_id: string;
  kind: string;
  amount_pln: number;
  description: string;
  booking_date: string;
  plan_id: string | null;
};
export type CardAllocation = {
  id: string;
  transaction_id: string;
  amount_pln: number;
  principal_pln: number;
  plan_id: string | null;
  statement_id: string | null;
};
export type CreditCard = {
  account_id: string;
  limit_pln: number;
  apr: string;
  cycle_close_day: number;
  due_day: number;
  grace_days: number;
  version: number;
  debt_pln: number;
  available_pln: number;
  pending_debits_pln: number;
  overpayment_pln: number;
  overlimit_pln: number;
  plans: CardPlan[];
  statements: CardStatement[];
  charges: CardCharge[];
  allocations: CardAllocation[];
};
export type CardCandidate = {
  id: string;
  description: string;
  date: string;
  amount_pln: number;
};
export type CandidateKind = "source" | "payment" | "charge";
const base = (accountId: string) =>
  `/finance/accounts/${accountId}/credit-card`;

export function useCreditCard(accountId: string | null) {
  return useQuery({
    queryKey: ["finance", "credit-card", accountId],
    enabled: !!accountId,
    retry: false,
    queryFn: async () => {
      try {
        return (await api.get<CreditCard>(base(accountId!))).data;
      } catch (error) {
        if ((error as AxiosError).response?.status === 404) return null;
        throw error;
      }
    },
  });
}

export function useCardCandidates(
  accountId: string,
  kind: CandidateKind,
  offset = 0,
) {
  return useQuery({
    queryKey: ["finance", "credit-card", accountId, "candidates", kind, offset],
    queryFn: async () =>
      (
        await api.get<{ items: CardCandidate[]; total: number }>(
          `${base(accountId)}/candidates`,
          { params: { kind, offset, limit: 50 } },
        )
      ).data,
  });
}

export function useCardMutation<T = unknown>(
  accountId: string,
  path: string,
  method: "post" | "put" | "delete" = "post",
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: T) => {
      if (method === "delete")
        return (await api.delete(`${base(accountId)}${path}`)).data;
      return (await api[method](`${base(accountId)}${path}`, input)).data;
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["finance"] });
    },
  });
}

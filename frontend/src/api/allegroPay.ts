import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { invalidateFinanceLedger } from "./finance";

export type AllegroInstallment = {
  id: string;
  number: number;
  due_date: string;
  principal_pln: number;
  interest_pln: number;
  fees_pln: number;
  total_pln: number;
  paid_pln: number;
  remaining_pln: number;
  payments: { transaction_id: string; amount_pln: number }[];
};
export type AllegroProfile = {
  id: string;
  account_id: string;
  account_name: string;
  limit_pln: number | null;
  ledger_balance_pln: number;
  available_pln: number | null;
  scheduled_remaining_pln: number;
  scheduled_costs_pln: number;
  purchases: {
    id: string;
    name: string;
    purchase_date: string;
    principal_pln: number;
    transaction_id: string;
    installments: AllegroInstallment[];
  }[];
};

export function useAllegroPay() {
  return useQuery({
    queryKey: ["finance", "allegro-pay"],
    queryFn: async () =>
      (await api.get<AllegroProfile[]>("/finance/allegro-pay")).data,
  });
}

export function useAllegroPayCommand(path: string, method: "put" | "post") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (data: unknown) =>
      (await api.request({ method, url: `/finance/allegro-pay${path}`, data }))
        .data,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["finance", "allegro-pay"] });
      invalidateFinanceLedger(client);
    },
  });
}

export function useUnlinkAllegroPayment(profileId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (transactionId: string) =>
      api.delete(`/finance/allegro-pay/${profileId}/payments/${transactionId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["finance", "allegro-pay"] }),
  });
}

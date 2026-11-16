import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import type { Account } from "./finance";

export interface OpeningBalanceInput {
  amount_minor: number;
  date: string;
  fx_rate?: string;
}
export interface OpeningBalanceView {
  amount_minor: number;
  date: string;
  fx_rate: string | null;
  version: number;
  can_edit: boolean;
  blocked_reason: string | null;
}
interface OpeningBalanceMutation extends OpeningBalanceInput {
  id: string;
  key: string;
  expected_version: number;
  session: number;
  userId: string;
}

function currentScope(session: number, userId: string) {
  const state = useAuthStore.getState();
  return state.sessionVersion === session && state.user?.id === userId;
}

export async function refreshOpeningBalanceAccount(
  id: string,
  session: number,
  userId: string,
) {
  if (!currentScope(session, userId)) throw new Error("Sesja zmieniła się.");
  const { data } = await api.get<Account>(`/finance/accounts/${id}`);
  if (!currentScope(session, userId)) throw new Error("Sesja zmieniła się.");
  if (data.id !== id || !data.opening_balance)
    throw new Error("Nie udało się odczytać BO konta.");
  return data;
}

export function useUpdateOpeningBalance() {
  const client = useQueryClient();
  const session = useAuthStore((state) => state.sessionVersion);
  const userId = useAuthStore((state) => state.user?.id);
  return useMutation({
    mutationKey: ["finance", "opening-balance", userId, session],
    retry: false,
    mutationFn: async ({
      id,
      key,
      session: expectedSession,
      userId: expectedUser,
      ...body
    }: OpeningBalanceMutation) => {
      if (!currentScope(expectedSession, expectedUser))
        throw new Error("Sesja zmieniła się.");
      return (
        await api.put<OpeningBalanceView>(
          `/finance/accounts/${id}/opening-balance`,
          body,
          {
            headers: { "Idempotency-Key": key },
          },
        )
      ).data;
    },
    onSuccess: (_result, input) => {
      if (!currentScope(input.session, input.userId)) return;
      // A replay can contain an older receipt, so refetch canonical ledger reads.
      for (const key of [
        "accounts",
        "transactions",
        "summary",
        "cashflow",
        "credit-card",
        "credit-cards",
        "budget-status",
        "category-summary",
      ])
        client.invalidateQueries({ queryKey: ["finance", key] });
    },
  });
}

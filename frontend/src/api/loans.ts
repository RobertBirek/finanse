import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import api from "../lib/api";
import { parsePlnToGrosze, type Account } from "./finance";

export type LoanPaymentStatus = "unpaid" | "partial" | "paid";
export type LoanPayment = {
  id: string;
  transaction_id: string;
  transaction_date: string;
  amount_pln: number;
};
export type LoanInstallment = {
  id: string;
  number: number;
  due_date: string;
  principal_pln: number;
  interest_pln: number;
  fees_pln: number;
  total_pln: number;
  paid_pln: number;
  remaining_pln: number;
  payment_status: LoanPaymentStatus;
  payments: LoanPayment[];
};
export type Loan = {
  id: string;
  name: string;
  account_id: string;
  payment_account_id: string;
  is_active: boolean;
  currency: "PLN";
  ledger_balance_pln: number;
  planned_principal_pln: number;
  planned_interest_pln: number;
  planned_fees_pln: number;
  total_planned_pln: number;
  paid_pln: number;
  remaining_pln: number;
  requires_accounting_review: boolean;
};
export type LoanDetail = Loan & { installments: LoanInstallment[] };
export type LoanCandidate = {
  transaction_id: string;
  transaction_date: string;
  description: string;
  amount_pln: number;
};
export type LoanCandidates = {
  items: LoanCandidate[];
  total: number;
  limit: number;
  offset: number;
};
export type LoanInput = {
  name: string;
  account_id: string;
  payment_account_id: string;
};
export type LoanInstallmentInput = {
  number: number;
  due_date: string;
  principal_pln: number;
  interest_pln: number;
  fees_pln: number;
};

export function loanAmountToGrosze(raw: string): number | null {
  return parsePlnToGrosze(raw, true);
}

export function loanApiErrorMessage(error: unknown): string | null {
  const detail = (error as AxiosError<{ detail?: unknown }> | undefined)
    ?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return "Nie udało się zapisać danych. Sprawdź formularz i spróbuj ponownie.";
  return error ? "Nie udało się wykonać operacji. Spróbuj ponownie." : null;
}

function invalidateLoans(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["finance", "loans"] });
}
export function useLoans() {
  return useQuery({
    queryKey: ["finance", "loans"],
    queryFn: async () => (await api.get<Loan[]>("/finance/loans")).data,
  });
}
export function useLoan(id: string | null) {
  return useQuery({
    queryKey: ["finance", "loans", id],
    enabled: !!id,
    queryFn: async () =>
      (await api.get<LoanDetail>(`/finance/loans/${id}`)).data,
  });
}
export function useCreateLoan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: LoanInput) =>
      (await api.post<LoanDetail>("/finance/loans", input)).data,
    onSuccess: () => invalidateLoans(client),
  });
}
export function useUpdateLoan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      ...input
    }: {
      id: string;
      name?: string;
      is_active?: boolean;
    }) => (await api.patch<Loan>(`/finance/loans/${id}`, input)).data,
    onSuccess: () => invalidateLoans(client),
  });
}
export function useCreateLoanInstallment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      loanId,
      ...input
    }: LoanInstallmentInput & { loanId: string }) =>
      (
        await api.post<LoanInstallment>(
          `/finance/loans/${loanId}/installments`,
          input,
        )
      ).data,
    onSuccess: () => invalidateLoans(client),
  });
}
export function useUpdateLoanInstallment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      loanId,
      installmentId,
      ...input
    }: Partial<LoanInstallmentInput> & {
      loanId: string;
      installmentId: string;
    }) =>
      (
        await api.patch<LoanInstallment>(
          `/finance/loans/${loanId}/installments/${installmentId}`,
          input,
        )
      ).data,
    onSuccess: () => invalidateLoans(client),
  });
}
export function useDeleteLoanInstallment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      loanId,
      installmentId,
    }: {
      loanId: string;
      installmentId: string;
    }) => {
      await api.delete(
        `/finance/loans/${loanId}/installments/${installmentId}`,
      );
    },
    onSuccess: () => invalidateLoans(client),
  });
}
export function useLoanPaymentCandidates(
  loanId: string | null,
  installmentId: string | null,
  offset: number,
) {
  return useQuery({
    queryKey: ["finance", "loans", loanId, installmentId, "candidates", offset],
    enabled: !!loanId && !!installmentId,
    queryFn: async () =>
      (
        await api.get<LoanCandidates>(
          `/finance/loans/${loanId}/installments/${installmentId}/payment-candidates`,
          { params: { limit: 20, offset } },
        )
      ).data,
  });
}
export function useLinkLoanPayment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      loanId,
      installmentId,
      transactionId,
    }: {
      loanId: string;
      installmentId: string;
      transactionId: string;
    }) =>
      (
        await api.post<LoanDetail>(
          `/finance/loans/${loanId}/installments/${installmentId}/payments`,
          { transaction_id: transactionId },
        )
      ).data,
    onSuccess: () => invalidateLoans(client),
  });
}
export function useUnlinkLoanPayment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      loanId,
      linkId,
    }: {
      loanId: string;
      linkId: string;
    }) => {
      await api.delete(`/finance/loans/${loanId}/payments/${linkId}`);
    },
    onSuccess: () => invalidateLoans(client),
  });
}

export function eligibleLoanAccounts(accounts: Account[]) {
  return accounts.filter(
    (account) => account.is_active && account.currency === "PLN",
  );
}

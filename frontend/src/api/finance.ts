import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface Account {
  id: string;
  name: string;
  type: string;
  currency: string;
  is_active: boolean;
  balance_pln: number;
  opened_at: string;
  closed_at: string | null;
}

export interface Category {
  id: string;
  name: string;
  parent_id: string | null;
  type: "income" | "expense" | "transfer";
}

export interface Posting {
  id: string;
  transaction_id: string;
  account_id: string;
  category_id: string | null;
  source_amount: number;
  source_currency: string;
  base_amount_pln: number;
  fx_rate: number;
  direction: "debit" | "credit";
}

export interface Transaction {
  id: string;
  transaction_date: string;
  description: string;
  type: "income" | "expense" | "transfer" | "exchange";
  is_pending: boolean;
  project_id: string | null;
  source: string;
  postings: Posting[];
}

export interface FinancialSummary {
  accounts: Array<{ id: string; name: string; balance_pln: number; currency: string }>;
  income_total_pln: number;
  expense_total_pln: number;
  net_total_pln: number;
  month: number;
  year: number;
}

export function useAccounts() {
  return useQuery({
    queryKey: ["finance", "accounts"],
    queryFn: async () => {
      const { data } = await api.get<Account[]>("/finance/accounts");
      return data;
    },
  });
}

export function useAccount(id: string | null) {
  return useQuery({
    queryKey: ["finance", "accounts", id],
    queryFn: async () => {
      const { data } = await api.get<Account>(`/finance/accounts/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (account: { name: string; type: string; currency?: string }) => {
      const { data } = await api.post<Account>("/finance/accounts", account);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
    },
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["finance", "categories"],
    queryFn: async () => {
      const { data } = await api.get<Category[]>("/finance/categories");
      return data;
    },
  });
}

export function useTransactions(params?: { account_id?: string; limit?: number }) {
  return useQuery({
    queryKey: ["finance", "transactions", params],
    queryFn: async () => {
      const { data } = await api.get<Transaction[]>("/finance/transactions", { params });
      return data;
    },
  });
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tx: {
      date?: string;
      description: string;
      type: string;
      is_pending?: boolean;
      project_id?: string;
      postings: Array<{
        account_id: string;
        category_id?: string;
        source_amount: number;
        source_currency?: string;
        base_amount_pln: number;
        direction: "debit" | "credit";
      }>;
    }) => {
      const { data } = await api.post<Transaction>("/finance/transactions", tx);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["finance", "transactions"] });
      queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
      queryClient.invalidateQueries({ queryKey: ["finance", "summary"] });
    },
  });
}

export function useFinancialSummary(month?: number, year?: number) {
  const now = new Date();
  const m = month ?? now.getMonth() + 1;
  const y = year ?? now.getFullYear();

  return useQuery({
    queryKey: ["finance", "summary", { month: m, year: y }],
    queryFn: async () => {
      const { data } = await api.get<FinancialSummary>("/finance/summary", {
        params: { month: m, year: y },
      });
      return data;
    },
  });
}

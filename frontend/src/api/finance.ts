import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import api from "../lib/api";

export interface Account {
  id: string;
  name: string;
  type: string;
  currency: string;
  is_active: boolean;
  is_budget_account: boolean;
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
  account_id: string | null;
  category_id: string | null;
  source_amount: number;
  source_currency: string;
  base_amount_pln: number;
  fx_rate: number;
  is_budget_impact: boolean;
  direction: "debit" | "credit";
}

export interface ExchangeInput {
  from_account_id: string;
  to_account_id: string;
  from_amount: number;
  fx_rate?: number | null;
  transaction_date?: string;
  description: string;
}

export interface PostingInput {
  account_id: string | null;
  category_id: string | null;
  source_amount: number;
  source_currency: string;
  base_amount_pln: number;
  fx_rate: number;
  fx_rate_source: string;
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
  accounts: Array<{
    id: string;
    name: string;
    balance_pln: number;
    currency: string;
  }>;
  income_total_pln: number;
  expense_total_pln: number;
  net_total_pln: number;
  month: number;
  year: number;
}

export interface FinancialPeriod {
  month?: number;
  year?: number;
}

export interface CategorySpend {
  category_id: string;
  name: string;
  parent_id: string | null;
  total_pln: number;
}

export interface CategorySummary {
  month: number;
  year: number;
  groups: CategorySpend[];
  categories: CategorySpend[];
}

export interface CategoryGroup extends CategorySpend {
  children: CategorySpend[];
}

export interface CategoryBudget {
  id: string;
  category_id: string;
  amount_pln: number;
}

export interface BudgetStatusItem {
  category_id: string;
  name: string;
  parent_id: string | null;
  budget_amount_pln: number;
  spent_pln: number;
  remaining_pln: number;
}

export interface BudgetStatusResponse {
  month: number;
  year: number;
  items: BudgetStatusItem[];
}

export interface ScheduledFinanceItem {
  id: string;
  name: string;
  type: "income" | "expense";
  account_id: string;
  category_id: string;
  currency: string;
  cadence: "monthly";
  due_day: number;
  amount_method: "fixed" | "last_actual";
  fixed_amount_pln: number | null;
  is_active: boolean;
}

export interface FinanceSettings {
  payday_day: number;
  payday_account_id: string | null;
  forecast_horizon_days: number;
  overdue_grace_days: number;
}

export interface FinanceSettingsUpdate {
  payday_day?: number;
  payday_account_id?: string | null;
  forecast_horizon_days?: number;
  overdue_grace_days?: number;
}

export interface ScheduledFinanceItemInput {
  name: string;
  type: "income" | "expense";
  account_id: string;
  category_id: string;
  currency: string;
  due_day: number;
  amount_method: "fixed" | "last_actual";
  fixed_amount_pln: number | null;
}

export interface ScheduledFinanceConfirmation {
  transaction: Transaction;
}

export type CashflowStatus =
  "due" | "overdue" | "overdue_uncertain" | "matched_actual" | "amount_unknown";

export interface CashflowSuggestion {
  scheduled_item_id: string;
  name: string;
  type: "income" | "expense";
  due_date: string;
  amount_pln: number | null;
  status: CashflowStatus;
  included_in_forecast: boolean;
  actual_transaction_id: string | null;
}

export interface CashflowBudgetSummary {
  total_budget_pln: number;
  total_spent_pln: number;
  remaining_pln: number;
}

export interface CashflowForecast {
  last_payday: string;
  next_payday: string;
  opening_balance_pln: number;
  projected_balance_before_next_payday_pln: number;
  safe_daily_limit_pln: number;
  lowest_balance_pln: number;
  days: Array<{ date: string; projected_balance_pln: number }>;
  suggestions: CashflowSuggestion[];
  budgets: CashflowBudgetSummary;
}

export function cashflowStatusLabel(status: CashflowStatus) {
  const labels: Record<CashflowStatus, string> = {
    due: "Zaplanowane",
    overdue: "Po terminie",
    overdue_uncertain: "Po terminie - kwota niepewna",
    matched_actual: "Zaksięgowane",
    amount_unknown: "Brak ostatniej kwoty",
  };
  return labels[status];
}

export function splitAccounts(accounts: Account[]) {
  return {
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  };
}

export function budgetProgress(
  budgetAmount: number,
  spent: number,
): { percent: number; over: boolean } {
  const raw = Math.round((spent / budgetAmount) * 1000) / 10;
  const percent = Math.max(0, Math.min(100, raw));
  return { percent, over: spent > budgetAmount };
}

export function buildCategoryTree(summary: CategorySummary): CategoryGroup[] {
  const groupsById = new Set(summary.groups.map((group) => group.category_id));
  const childrenByGroup = new Map<string, CategorySpend[]>();

  for (const category of summary.categories) {
    if (category.parent_id === null) continue;
    const children = childrenByGroup.get(category.parent_id) ?? [];
    children.push(category);
    childrenByGroup.set(category.parent_id, children);
  }

  return [
    ...summary.groups.map((group) => ({
      ...group,
      children: childrenByGroup.get(group.category_id) ?? [],
    })),
    ...summary.categories
      .filter(
        (category) =>
          category.parent_id === null && !groupsById.has(category.category_id),
      )
      .map((category) => ({ ...category, children: [] })),
  ];
}

export function parsePlnToGrosze(raw: string): number | null {
  const normalized = raw.replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;

  const [whole, fractional = ""] = normalized.split(".");
  const grosze = Number(whole) * 100 + Number(fractional.padEnd(2, "0"));

  return Number.isSafeInteger(grosze) && grosze > 0 ? grosze : null;
}

export function buildTransactionPostings(
  input:
    | {
        type: "income" | "expense";
        accountId: string;
        categoryId: string;
        amountPlng: number;
      }
    | {
        type: "transfer";
        fromAccountId: string;
        toAccountId: string;
        amountPlng: number;
      },
): PostingInput[] {
  const base = {
    source_amount: input.amountPlng,
    source_currency: "PLN",
    base_amount_pln: input.amountPlng,
    fx_rate: 1,
    fx_rate_source: "manual",
  };

  if (input.type === "transfer") {
    return [
      {
        ...base,
        account_id: input.fromAccountId,
        category_id: null,
        direction: "debit",
      },
      {
        ...base,
        account_id: input.toAccountId,
        category_id: null,
        direction: "credit",
      },
    ];
  }

  const accountCredited = input.type === "income";
  return [
    {
      ...base,
      account_id: input.accountId,
      category_id: null,
      direction: accountCredited ? "credit" : "debit",
    },
    {
      ...base,
      account_id: null,
      category_id: input.categoryId,
      direction: accountCredited ? "debit" : "credit",
    },
  ];
}

export function canConfirmSuggestion(
  suggestion: Pick<CashflowSuggestion, "status" | "amount_pln" | "due_date">,
  todayIso: string,
): boolean {
  return (
    (suggestion.status === "due" || suggestion.status === "overdue") &&
    suggestion.amount_pln !== null &&
    suggestion.amount_pln > 0 &&
    suggestion.due_date <= todayIso
  );
}

function invalidateCashflowMutationQueries(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["finance", "cashflow"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "transactions"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "summary"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "category-summary"] });
}

function normalizeScheduledFinanceItemInput(
  item: ScheduledFinanceItemInput,
): ScheduledFinanceItemInput {
  return item.amount_method === "last_actual"
    ? { ...item, fixed_amount_pln: null }
    : item;
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
    mutationFn: async (account: {
      name: string;
      type: string;
      currency?: string;
    }) => {
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

export function useTransactions(params?: {
  account_id?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["finance", "transactions", params],
    queryFn: async () => {
      const { data } = await api.get<Transaction[]>("/finance/transactions", {
        params,
      });
      return data;
    },
  });
}

export function useAccountTransactions(
  accountId: string | null,
  params?: { limit?: number },
) {
  return useQuery({
    queryKey: ["finance", "accounts", accountId, "transactions", params],
    queryFn: async () => {
      const { data } = await api.get<Transaction[]>(
        `/finance/accounts/${accountId}/transactions`,
        { params },
      );
      return data;
    },
    enabled: !!accountId,
  });
}

export function invalidateFinanceLedger(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["finance", "transactions"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "summary"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "category-summary"] });
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tx: {
      transaction_date?: string;
      description: string;
      type: string;
      is_pending?: boolean;
      project_id?: string;
      postings: PostingInput[];
    }) => {
      const { data } = await api.post<Transaction>("/finance/transactions", tx);
      return data;
    },
    onSuccess: () => invalidateFinanceLedger(queryClient),
  });
}

export function useCreateExchange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ExchangeInput) => {
      const { fx_rate, transaction_date, ...rest } = input;
      const payload = {
        ...rest,
        ...(fx_rate != null ? { fx_rate } : {}),
        ...(transaction_date !== undefined ? { transaction_date } : {}),
      };
      const { data } = await api.post<Transaction>(
        "/finance/transactions/exchange",
        payload,
      );
      return data;
    },
    onSuccess: () => invalidateFinanceLedger(queryClient),
  });
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      transaction_date,
      description,
    }: {
      id: string;
      transaction_date?: string;
      description?: string;
    }) => {
      const { data } = await api.patch<Transaction>(
        `/finance/transactions/${id}`,
        { transaction_date, description },
      );
      return data;
    },
    onSuccess: () => invalidateFinanceLedger(queryClient),
  });
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/finance/transactions/${id}`);
    },
    onSuccess: () => invalidateFinanceLedger(queryClient),
  });
}

export function useFinancialSummary(period?: FinancialPeriod) {
  const now = new Date();
  const m = period?.month ?? now.getMonth() + 1;
  const y = period?.year ?? now.getFullYear();

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

export function useCategorySummary(period?: FinancialPeriod) {
  const now = new Date();
  const m = period?.month ?? now.getMonth() + 1;
  const y = period?.year ?? now.getFullYear();

  return useQuery({
    queryKey: ["finance", "category-summary", { month: m, year: y }],
    queryFn: async () => {
      const { data } = await api.get<CategorySummary>(
        "/finance/category-summary",
        { params: { month: m, year: y } },
      );
      return data;
    },
  });
}

function invalidateBudgetMutationQueries(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ["finance", "budgets"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "budget-status"] });
  queryClient.invalidateQueries({ queryKey: ["finance", "category-summary"] });
}

export function useBudgets() {
  return useQuery({
    queryKey: ["finance", "budgets"],
    queryFn: async () => {
      const { data } = await api.get<CategoryBudget[]>("/finance/budgets");
      return data;
    },
  });
}

export function useCreateBudget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (budget: { category_id: string; amount_pln: number }) => {
      const { data } = await api.post<CategoryBudget>(
        "/finance/budgets",
        budget,
      );
      return data;
    },
    onSuccess: () => invalidateBudgetMutationQueries(queryClient),
  });
}

export function useUpdateBudget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      amount_pln,
    }: {
      id: string;
      amount_pln: number;
    }) => {
      const { data } = await api.patch<CategoryBudget>(
        `/finance/budgets/${id}`,
        { amount_pln },
      );
      return data;
    },
    onSuccess: () => invalidateBudgetMutationQueries(queryClient),
  });
}

export function useDeleteBudget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/finance/budgets/${id}`);
    },
    onSuccess: () => invalidateBudgetMutationQueries(queryClient),
  });
}

export function useBudgetStatus(period?: FinancialPeriod) {
  const now = new Date();
  const m = period?.month ?? now.getMonth() + 1;
  const y = period?.year ?? now.getFullYear();

  return useQuery({
    queryKey: ["finance", "budget-status", { month: m, year: y }],
    queryFn: async () => {
      const { data } = await api.get<BudgetStatusResponse>(
        "/finance/budget-status",
        { params: { month: m, year: y } },
      );
      return data;
    },
  });
}

export function useCashflowForecast() {
  return useQuery({
    queryKey: ["finance", "cashflow", "forecast"],
    queryFn: async () => {
      const { data } = await api.get<CashflowForecast>(
        "/finance/cashflow/forecast",
      );
      return data;
    },
  });
}

export function useCashflowSettings() {
  return useQuery({
    queryKey: ["finance", "cashflow", "settings"],
    queryFn: async () => {
      const { data } = await api.get<FinanceSettings>(
        "/finance/cashflow/settings",
      );
      return data;
    },
  });
}

export function useUpdateCashflowSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (settings: FinanceSettingsUpdate) => {
      const { data } = await api.patch<FinanceSettings>(
        "/finance/cashflow/settings",
        settings,
      );
      return data;
    },
    onSuccess: () => invalidateCashflowMutationQueries(queryClient),
  });
}

export function useScheduledFinanceItems() {
  return useQuery({
    queryKey: ["finance", "cashflow", "items"],
    queryFn: async () => {
      const { data } = await api.get<ScheduledFinanceItem[]>(
        "/finance/cashflow/items",
      );
      return data;
    },
  });
}

export function useCreateScheduledFinanceItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (item: ScheduledFinanceItemInput) => {
      const { data } = await api.post<ScheduledFinanceItem>(
        "/finance/cashflow/items",
        normalizeScheduledFinanceItemInput(item),
      );
      return data;
    },
    onSuccess: () => invalidateCashflowMutationQueries(queryClient),
  });
}

export function useUpdateScheduledFinanceItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      is_active,
      ...item
    }: ScheduledFinanceItemInput & { id: string; is_active?: boolean }) => {
      const normalizedItem = normalizeScheduledFinanceItemInput(item);
      const update = {
        name: normalizedItem.name,
        account_id: normalizedItem.account_id,
        category_id: normalizedItem.category_id,
        currency: normalizedItem.currency,
        due_day: normalizedItem.due_day,
        amount_method: normalizedItem.amount_method,
        fixed_amount_pln: normalizedItem.fixed_amount_pln,
        ...(is_active !== undefined ? { is_active } : {}),
      };
      const { data } = await api.patch<ScheduledFinanceItem>(
        `/finance/cashflow/items/${id}`,
        update,
      );
      return data;
    },
    onSuccess: () => invalidateCashflowMutationQueries(queryClient),
  });
}

export function useDeleteScheduledFinanceItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/finance/cashflow/items/${id}`);
    },
    onSuccess: () => invalidateCashflowMutationQueries(queryClient),
  });
}

export function useConfirmScheduledFinanceItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post<ScheduledFinanceConfirmation>(
        `/finance/cashflow/items/${id}/confirm`,
      );
      return data;
    },
    onSuccess: () => invalidateCashflowMutationQueries(queryClient),
  });
}

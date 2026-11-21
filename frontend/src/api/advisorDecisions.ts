import { useMutation } from "@tanstack/react-query";
import api from "../lib/api";

export type Attention = {
  as_of: string;
  items: {
    kind: "payment" | "document" | "task";
    source_id: string;
    title: string;
    reason: string;
    due_date: string | null;
    href: string;
  }[];
};

export type Explanation = {
  status: "ok" | "unavailable" | "no_facts";
  text: string | null;
};

export type ScenarioInput = { expense_date: string; amount_pln_minor: number };
export type SpendingDays = 14 | 30 | 90;
export type SpendingComparison = {
  previous_start: string;
  current_start: string;
  end_exclusive: string;
  previous_total_pln: number;
  current_total_pln: number;
  delta_pln: number;
  categories: { category_id: string; name: string; delta_pln: number }[];
  transactions: {
    transaction_id: string;
    date: string;
    description: string;
    delta_pln: number;
  }[];
  truncated: boolean;
};
type BalancePoint = { date: string; projected_balance_pln: number };
export type Scenario = {
  baseline_minimum: BalancePoint;
  scenario_minimum: BalancePoint;
  first_negative_date: string | null;
  opening_balance_negative: boolean;
  next_payday: string;
  forecast_start: string;
  forecast_end: string;
  excluded_obligation_reasons: string[];
  covers_day_before_payday: boolean;
};

export function useAttention() {
  return useMutation({
    mutationFn: async () =>
      (await api.get<Attention>("/advisor/decisions/attention")).data,
  });
}

export function useAttentionExplanation() {
  return useMutation({
    mutationFn: async () =>
      (await api.post<Explanation>("/advisor/decisions/attention/explain"))
        .data,
  });
}

export function useScenario() {
  return useMutation({
    mutationFn: async (input: ScenarioInput) =>
      (await api.post<Scenario>("/advisor/decisions/cashflow-scenario", input))
        .data,
  });
}

export function useScenarioExplanation() {
  return useMutation({
    mutationFn: async (input: ScenarioInput) =>
      (
        await api.post<Explanation>(
          "/advisor/decisions/cashflow-scenario/explain",
          input,
        )
      ).data,
  });
}

export function useSpendingComparison() {
  return useMutation({
    mutationFn: async (days: SpendingDays) =>
      (
        await api.get<SpendingComparison>(
          "/advisor/decisions/spending-comparison",
          {
            params: { days },
          },
        )
      ).data,
  });
}

export function useSpendingExplanation() {
  return useMutation({
    mutationFn: async (days: SpendingDays) =>
      (
        await api.post<Explanation>(
          "/advisor/decisions/spending-comparison/explain",
          undefined,
          {
            params: { days },
          },
        )
      ).data,
  });
}

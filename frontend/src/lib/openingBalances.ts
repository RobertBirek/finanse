import type {
  OpeningBalanceInput,
  OpeningBalanceView,
} from "../api/openingBalances";
import { localTodayIso } from "./date";

export interface OpeningBalanceDraft {
  amount: string;
  date: string;
  fxRate: string;
}

export function parseSignedMinor(raw: string): number | null {
  const normalized = raw.replace(/\s/g, "").replace(",", ".");
  if (!normalized) return 0;
  const match = /^([+-]?)(\d+)(?:\.(\d{1,2}))?$/.exec(normalized);
  if (!match) return null;
  const amount = Number(match[2] + (match[3] ?? "").padEnd(2, "0"));
  if (!Number.isSafeInteger(amount)) return null;
  return amount === 0 ? 0 : match[1] === "-" ? -amount : amount;
}

export function openingBalancePayload(
  value: OpeningBalanceDraft,
  currency: string,
): OpeningBalanceInput | null {
  const amount = parseSignedMinor(value.amount);
  const parsedDate = new Date(`${value.date}T00:00:00Z`);
  if (
    amount === null ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.date) ||
    !Number.isFinite(parsedDate.getTime()) ||
    parsedDate.toISOString().slice(0, 10) !== value.date
  )
    return null;
  const result: OpeningBalanceInput = {
    amount_minor: amount,
    date: value.date,
  };
  if (currency !== "PLN" && amount !== 0) {
    const rate = value.fxRate.trim().replace(",", ".");
    if (
      !/^\d+(?:\.\d{1,6})?$/.test(rate) ||
      Number(rate) <= 0 ||
      Number(rate) >= 1_000_000
    )
      return null;
    result.fx_rate = rate;
  }
  return result;
}

export function openingBalanceDraft(
  value?: OpeningBalanceView | null,
): OpeningBalanceDraft {
  if (!value) return { amount: "", date: localTodayIso(), fxRate: "" };
  const absolute = Math.abs(value.amount_minor);
  return {
    amount: `${value.amount_minor < 0 ? "-" : ""}${Math.trunc(absolute / 100)},${String(absolute % 100).padStart(2, "0")}`,
    date: value.date,
    fxRate: value.fx_rate ?? "",
  };
}

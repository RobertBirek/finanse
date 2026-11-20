import type { Posting } from "../api/finance";

export function formatPLN(amount: number) {
  return new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}

export function formatPostingAmount(posting: Posting | undefined): string {
  if (!posting) return "Kwota niedostępna";
  const sign = posting.direction === "credit" ? "+" : "−";
  return `${sign}${formatPLN(posting.source_amount)} ${posting.source_currency}`;
}

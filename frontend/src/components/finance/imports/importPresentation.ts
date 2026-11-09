import type { ImportSource } from "../../../api/bankImports";

export function sourceMoney(amount: number, currency: string) {
  return `${new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount / 100)} ${currency}`;
}
export function isSourceBlocked(source: ImportSource) {
  return (
    source.validation_state === "blocked" ||
    source.checks.some((check) => check.required && check.result !== "passed")
  );
}

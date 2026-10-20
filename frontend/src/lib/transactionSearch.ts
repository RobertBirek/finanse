import type { TransactionSearchParams } from "../api/finance";

export const SEARCH_FIELDS = [
  "q",
  "account_id",
  "category_id",
  "date_from",
  "date_to",
  "currency",
  "type",
  "min",
  "max",
  "size",
] as const;

export function parseSearchAmount(value: string): number | undefined {
  if (!value.trim()) return undefined;
  if (!/^\d{1,14}([,.]\d{1,2})?$/.test(value.trim()))
    throw new Error(
      "Podaj nieujemną kwotę z maksymalnie 2 miejscami po przecinku.",
    );
  const [units, fraction = ""] = value.trim().replace(",", ".").split(".");
  const minor = BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (minor > BigInt(Number.MAX_SAFE_INTEGER))
    throw new Error("Podana kwota jest zbyt duża.");
  return Number(minor);
}

export function transactionSearchParams(
  search: URLSearchParams,
): TransactionSearchParams {
  const text = (name: string) => search.get(name)?.trim() || undefined;
  const q = text("q");
  if (q && q.length > 200)
    throw new Error("Wyszukiwana fraza może mieć maksymalnie 200 znaków.");
  const date_from = text("date_from"),
    date_to = text("date_to");
  for (const day of [date_from, date_to]) {
    if (
      day &&
      (!/^\d{4}-\d{2}-\d{2}$/.test(day) ||
        Number.isNaN(Date.parse(day)) ||
        new Date(day).toISOString().slice(0, 10) !== day)
    )
      throw new Error("Podaj poprawne daty.");
  }
  if (date_from && date_to && date_from > date_to)
    throw new Error("Data od nie może być późniejsza niż data do.");
  const min_amount_pln = parseSearchAmount(text("min") ?? "");
  const max_amount_pln = parseSearchAmount(text("max") ?? "");
  if (
    min_amount_pln !== undefined &&
    max_amount_pln !== undefined &&
    min_amount_pln > max_amount_pln
  )
    throw new Error("Kwota od nie może być większa niż kwota do.");
  const currency = text("currency"),
    type = text("type");
  if (currency && !["PLN", "EUR", "USD"].includes(currency))
    throw new Error("Wybierz obsługiwaną walutę.");
  if (type && !["income", "expense", "transfer", "exchange"].includes(type))
    throw new Error("Wybierz poprawny typ transakcji.");
  const size = Number(text("size") ?? 25);
  const page = Number(text("page") ?? 1);
  if (
    ![25, 50, 100].includes(size) ||
    !Number.isSafeInteger(page) ||
    page < 1 ||
    (page - 1) * size > 10000000
  )
    throw new Error(
      "Nieprawidłowy numer lub rozmiar strony. Wyczyść filtry, aby wrócić do listy.",
    );
  return {
    q,
    account_id: text("account_id"),
    category_id: text("category_id"),
    date_from,
    date_to,
    currency,
    type,
    min_amount_pln,
    max_amount_pln,
    limit: size,
    offset: (page - 1) * size,
  };
}

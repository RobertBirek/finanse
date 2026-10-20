import type { AxiosError } from "axios";

export const MUTATION_ERROR_MESSAGE =
  "Nie udało się zapisać zmian. Sprawdź dane i spróbuj ponownie.";

export function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  const detail: unknown = (error as AxiosError<{ detail?: unknown }>)?.response
    ?.data?.detail;
  // FastAPI validation errors contain an array of objects, not renderable text.
  return typeof detail === "string" && detail.trim()
    ? detail
    : MUTATION_ERROR_MESSAGE;
}

export function isConflict(error: unknown): boolean {
  return (error as AxiosError)?.response?.status === 409;
}

export const ACCOUNT_TYPES = [
  { value: "checking", label: "Bieżące" },
  { value: "savings", label: "Oszczędnościowe" },
  { value: "cash", label: "Gotówka" },
  { value: "credit", label: "Kredytowe" },
  { value: "investment", label: "Inwestycyjne" },
] as const;

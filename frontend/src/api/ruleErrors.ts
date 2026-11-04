import type { AxiosError } from "axios";

export function ruleError(error: unknown) {
  const response = (error as AxiosError<{ detail?: string }>).response;
  return {
    stale: response?.status === 409,
    uncertain: !response || response.status >= 500,
    message:
      typeof response?.data.detail === "string"
        ? response.data.detail
        : "Nie udało się zapisać. Wpisane wartości i klucz ponowienia zostały zachowane.",
  };
}

import type { CardConfig, CardSettings } from "../../api/creditCards";
import { parsePlnToGrosze } from "../../api/finance";

export type CardDraft = {
  limit: string;
  apr: string;
  cycle: string;
  due: string;
  grace: string;
};

export function cardDraft(settings?: CardSettings | null): CardDraft {
  const limit = settings?.limit_pln;
  return {
    limit:
      limit === undefined
        ? ""
        : `${Math.floor(limit / 100)}${limit % 100 ? `.${String(limit % 100).padStart(2, "0")}` : ""}`,
    apr: settings?.apr ?? "",
    cycle: settings ? String(settings.cycle_close_day) : "",
    due: settings ? String(settings.due_day) : "",
    grace: settings ? String(settings.grace_days) : "",
  };
}

export function cardConfig(
  draft: CardDraft,
  version: number,
): CardConfig | null {
  const limit = parsePlnToGrosze(draft.limit, true);
  const apr = draft.apr.trim().replace(",", ".");
  const day = (value: string, low: number, high: number) =>
    /^\d+$/.test(value) && Number(value) >= low && Number(value) <= high;
  if (
    limit === null ||
    limit <= 0 ||
    !/^\d{1,3}(\.\d{1,4})?$/.test(apr) ||
    Number(apr) > 100 ||
    !day(draft.cycle, 1, 31) ||
    !day(draft.due, 1, 31) ||
    !day(draft.grace, 0, 366)
  )
    return null;
  return {
    limit_pln: limit,
    apr,
    cycle_close_day: Number(draft.cycle),
    due_day: Number(draft.due),
    grace_days: Number(draft.grace),
    expected_version: version,
  };
}

export const CARD_SETTINGS_ERROR =
  "Sprawdź warunki karty: dodatni limit, oprocentowanie 0–100%, dni 1–31 i okres bezodsetkowy 0–366 dni.";

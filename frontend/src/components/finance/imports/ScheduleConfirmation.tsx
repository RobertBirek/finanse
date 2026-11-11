import { useState } from "react";
import type { SchedulePreview } from "../../../api/loanScheduleImports";

export function ScheduleConfirmation({
  preview,
  current,
  pending,
  onActivate,
}: {
  preview: SchedulePreview;
  current: boolean;
  pending: boolean;
  onActivate: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  return (
    <section className="card space-y-4" aria-label="Potwierdzenie harmonogramu">
      <h2 className="text-xl">Aktualizacja planu, nie księgowanie</h2>
      <p className="text-sm">
        Data obowiązywania według banku:{" "}
        {preview.bank_effective_date ?? "sprawdź oryginał"} · granica zmiany
        planu: {preview.cutover_date}
      </p>
      <p>
        Aktywacja zachowa powiązania i identyfikatory zgodnych rat. Nie tworzy
        przelewów, nie zmienia salda i nie oznacza rat jako zapłaconych.
      </p>
      {!current ? (
        <p role="alert">
          Podgląd nieaktualny. Przygotuj nowy podgląd przed aktywacją.
        </p>
      ) : null}
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={pending}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        Potwierdzam aktualizację planu i zachowanie istniejących powiązań bez
        księgowania spłat
      </label>
      <button
        className="btn-primary"
        type="button"
        disabled={
          !current || pending || !confirmed || preview.diff.conflicts.length > 0
        }
        onClick={onActivate}
      >
        {pending ? "Aktywowanie…" : "Aktywuj harmonogram"}
      </button>
    </section>
  );
}

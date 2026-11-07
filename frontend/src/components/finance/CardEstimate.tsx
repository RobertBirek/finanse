import { useRef, useState, type FormEvent } from "react";
import { useCardMutation } from "../../api/creditCards";
import { parsePlnToGrosze } from "../../api/finance";
import { formatPLN } from "../../lib/format";

export function CardEstimate({
  accountId,
  apr,
}: {
  accountId: string;
  apr: string;
}) {
  const mutation = useCardMutation(accountId, "/interest-estimate");
  const [amount, setAmount] = useState("");
  const [days, setDays] = useState("");
  const [result, setResult] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const submittedGeneration = ++generation.current;
    setError(false);
    setResult(null);
    const principal = parsePlnToGrosze(amount, true);
    if (principal === null || !/^\d+$/.test(days)) {
      setError(true);
      return;
    }
    try {
      const response = await mutation.mutateAsync({
        principal_pln: principal,
        apr,
        days: Number(days),
      });
      if (!Number.isSafeInteger(response?.estimated_interest_pln))
        throw new Error("Invalid estimate");
      if (generation.current === submittedGeneration)
        setResult(response.estimated_interest_pln);
    } catch {
      if (generation.current === submittedGeneration) setError(true);
    }
  }
  return (
    <form
      aria-label="Szacunek odsetek"
      onSubmit={submit}
      className="card space-y-3"
    >
      <h3 className="text-lg font-semibold text-white">Szacunek odsetek</h3>
      <p className="text-sm text-gray-400">
        Proste odsetki ACT/365 przy {apr}% rocznie. Podaj tylko kapitał
        oprocentowany tą stopą, bez planów o innym oprocentowaniu. To nie
        wyliczenie bankowe: nie rozstrzyga okresu bezodsetkowego ani kolejności
        spłat i nie zmienia salda.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>
          Oprocentowany kapitał PLN
          <input
            aria-label="Oprocentowany kapitał PLN"
            className="input w-full"
            required
            inputMode="decimal"
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              generation.current += 1;
              setResult(null);
            }}
          />
        </label>
        <label>
          Liczba dni
          <input
            aria-label="Liczba dni"
            className="input w-full"
            required
            inputMode="numeric"
            value={days}
            onChange={(event) => {
              setDays(event.target.value);
              generation.current += 1;
              setResult(null);
            }}
          />
        </label>
      </div>
      <button className="btn-secondary" disabled={mutation.isPending}>
        Oblicz szacunek
      </button>
      {result !== null ? (
        <p role="status">
          Szacunek: {formatPLN(result)} PLN — niezaksięgowany.
        </p>
      ) : null}
      {error ? (
        <p role="alert">
          Nie udało się obliczyć szacunku. Sprawdź kwotę i liczbę dni.
        </p>
      ) : null}
    </form>
  );
}

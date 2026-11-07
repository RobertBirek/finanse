import { useRef, useState, type FormEvent } from "react";
import {
  useCardMutation,
  useCardCandidates,
  type CandidateKind,
} from "../../api/creditCards";
import { parsePlnToGrosze } from "../../api/finance";
import { formatPLN } from "../../lib/format";
import { loanApiErrorMessage } from "../../api/loans";

export type CardField = {
  name: string;
  label: string;
  type?: "money" | "integer" | "decimal" | "date" | "text";
  value?: string | number;
  optional?: boolean;
  options?: { value: string; label: string }[];
  candidates?: CandidateKind;
};

function CandidateSelect({
  accountId,
  field,
}: {
  accountId: string;
  field: CardField;
}) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const query = useCardCandidates(accountId, field.candidates!, offset);
  return (
    <div>
      <select
        className="input w-full"
        aria-label={field.label}
        name={field.name}
        required={!field.optional}
        value={selected}
        onChange={(event) => setSelected(event.target.value)}
        disabled={query.isLoading || query.isError}
      >
        <option value="">
          {query.isLoading ? "Ładowanie…" : "Wybierz transakcję"}
        </option>
        {query.data?.items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.date} · {item.description} · {formatPLN(item.amount_pln)} PLN
          </option>
        ))}
      </select>
      {query.isError ? (
        <p role="alert">Nie udało się pobrać transakcji. Odśwież dane.</p>
      ) : null}
      {(query.data?.total ?? 0) > 50 ? (
        <div className="flex gap-3 text-sm">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => {
              setOffset(Math.max(0, offset - 50));
              setSelected("");
            }}
          >
            Poprzednie transakcje
          </button>
          <button
            type="button"
            disabled={offset + 50 >= (query.data?.total ?? 0)}
            onClick={() => {
              setOffset(offset + 50);
              setSelected("");
            }}
          >
            Kolejne transakcje
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function CardForm({
  accountId,
  title,
  path,
  fields,
  extra = {},
  method = "post",
  submitLabel = "Zapisz",
  children,
}: {
  accountId: string;
  title: string;
  path: string;
  fields: CardField[];
  extra?: Record<string, unknown>;
  method?: "post" | "put";
  submitLabel?: string;
  children?: React.ReactNode;
}) {
  const mutation = useCardMutation<Record<string, unknown>>(
    accountId,
    path,
    method,
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const retry = useRef({ fingerprint: "", id: "" });
  const sending = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload: Record<string, unknown> = { ...extra };
    for (const field of fields) {
      const raw = String(values.get(field.name) ?? "").trim();
      if (!raw && field.optional) continue;
      if (field.type === "money") {
        const amount = parsePlnToGrosze(raw, true);
        if (amount === null) {
          setError(`Sprawdź kwotę: ${field.label}`);
          return;
        }
        payload[field.name] = amount;
      } else if (field.type === "integer") {
        if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
          setError(`Sprawdź liczbę: ${field.label}`);
          return;
        }
        payload[field.name] = Number(raw);
      } else
        payload[field.name] =
          field.type === "decimal" ? raw.replace(",", ".") : raw;
    }
    const fingerprint = JSON.stringify(payload);
    if (method === "post") {
      if (retry.current.fingerprint !== fingerprint)
        retry.current = { fingerprint, id: crypto.randomUUID() };
      payload.request_id = retry.current.id;
    }
    setError(null);
    setSaved(false);
    sending.current = true;
    try {
      await mutation.mutateAsync(payload);
      setSaved(true);
      if (method === "post") {
        form.reset();
        retry.current = { fingerprint: "", id: "" };
      }
    } catch (reason) {
      setError(
        `Nie udało się zapisać. ${loanApiErrorMessage(reason) ?? "Sprawdź dane."}`,
      );
    } finally {
      sending.current = false;
    }
  }
  return (
    <form aria-label={title} onSubmit={submit} className="card space-y-4">
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      {children}
      <fieldset
        disabled={mutation.isPending}
        className="grid gap-4 sm:grid-cols-2"
      >
        {fields.map((field) => (
          <label key={field.name} className="block text-sm text-gray-300">
            <span className="mb-1 block">{field.label}</span>
            {field.candidates ? (
              <CandidateSelect accountId={accountId} field={field} />
            ) : field.options ? (
              <select
                name={field.name}
                aria-label={field.label}
                defaultValue={field.value ?? ""}
                className="input w-full"
                required={!field.optional}
              >
                <option value="">Wybierz</option>
                {field.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                name={field.name}
                aria-label={field.label}
                required={!field.optional}
                defaultValue={field.value ?? ""}
                type={field.type === "date" ? "date" : "text"}
                inputMode={
                  field.type === "money" || field.type === "decimal"
                    ? "decimal"
                    : field.type === "integer"
                      ? "numeric"
                      : undefined
                }
                className="input w-full"
              />
            )}
          </label>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className="text-sm text-green-400">
          Zapisano.
        </p>
      ) : null}
      <button className="btn-primary" disabled={mutation.isPending}>
        {mutation.isPending ? "Zapisywanie…" : submitLabel}
      </button>
    </form>
  );
}

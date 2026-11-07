import { useState } from "react";
import {
  useCardMutation,
  type CardAllocation,
  type CreditCard,
} from "../../api/creditCards";
import { CardForm, type CardField } from "./CardForm";
import { formatPLN } from "../../lib/format";

function AllocationRow({
  accountId,
  item,
}: {
  accountId: string;
  item: CardAllocation;
}) {
  const mutation = useCardMutation(
    accountId,
    `/allocations/${item.id}`,
    "delete",
  );
  const [error, setError] = useState(false);
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 text-sm">
      <span>
        {item.plan_id ? "Spłata planu" : "Spłata wyciągu"}:{" "}
        {formatPLN(item.amount_pln)} PLN
      </span>
      <button
        type="button"
        className="btn-secondary"
        disabled={mutation.isPending}
        onClick={async () => {
          setError(false);
          try {
            await mutation.mutateAsync(undefined);
          } catch {
            setError(true);
          }
        }}
      >
        Cofnij powiązanie
      </button>
      {error ? (
        <span role="alert">Nie udało się cofnąć powiązania.</span>
      ) : null}
    </li>
  );
}

export function CardAllocations({
  accountId,
  card,
  targets,
}: {
  accountId: string;
  card: CreditCard;
  targets: { value: string; label: string }[];
}) {
  const [target, setTarget] = useState("");
  const [kind, id] = target.split(":");
  const fields: CardField[] = [
    { name: "transaction_id", label: "Przelew spłaty", candidates: "payment" },
    { name: "amount_pln", label: "Przypisana kwota PLN", type: "money" },
  ];
  if (kind === "plan")
    fields.push(
      ...[
        {
          name: "principal_pln",
          label: "Spłacony kapitał PLN",
          type: "money" as const,
        },
        {
          name: "interest_pln",
          label: "Spłacone odsetki PLN",
          type: "money" as const,
          value: "0",
        },
        {
          name: "fees_pln",
          label: "Spłacone opłaty PLN",
          type: "money" as const,
          value: "0",
        },
      ],
    );
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white">
        Spłaty i wcześniejsze zamknięcie
      </h2>
      <p className="text-sm text-gray-400">
        Najpierw zapisz lub zaimportuj przelew z własnego konta na kartę. Tutaj
        tylko przypisujesz go do rozliczenia. Ten sam przelew może opisywać
        spłatę wyciągu oraz planu — nie jest ponownie księgowany. Przy
        wcześniejszej spłacie podaj rzeczywisty kapitał i koszty bankowe, nie
        sumę przyszłych szacowanych odsetek.
      </p>
      <label className="block text-sm text-gray-300">
        Spłacany wyciąg lub plan
        <select
          aria-label="Spłacany wyciąg lub plan"
          className="input mt-1 w-full"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
        >
          <option value="">Wybierz rozliczenie</option>
          {targets.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {id ? (
        <CardForm
          key={target}
          accountId={accountId}
          title="Przypisz przelew spłaty"
          path="/allocations"
          fields={fields}
          extra={kind === "plan" ? { plan_id: id } : { statement_id: id }}
        />
      ) : null}
      <ul className="space-y-2">
        {card.allocations.map((item) => (
          <AllocationRow key={item.id} accountId={accountId} item={item} />
        ))}
      </ul>
    </section>
  );
}

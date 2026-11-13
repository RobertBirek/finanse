import { Link } from "react-router-dom";
import { usePeople } from "../../api/people";

export function AccountPersonLink({ accountId }: { accountId: string }) {
  const people = usePeople({
    reference_account_id: accountId,
    include_archived: true,
  });
  const person = people.data?.items[0];
  if (people.isError)
    return (
      <p className="text-sm text-gray-400">
        Nie udało się sprawdzić skrótu do osoby.{" "}
        <button className="underline" onClick={() => people.refetch()}>
          Ponów
        </button>
      </p>
    );
  return person ? (
    <p className="my-3">
      <Link
        className="text-advisor-400 underline"
        to={`/finances/people/${person.id}`}
      >
        Historia darowizn od tej osoby
      </Link>
      <span className="text-sm text-gray-400 block">
        Historia osoby jest niezależna od salda tego konta.
      </span>
    </p>
  ) : null;
}

import { useState } from "react";
import { useCardMutation } from "../../api/creditCards";
import { loanApiErrorMessage } from "../../api/loans";

export function CardRemoveRecord({
  accountId,
  path,
  label,
}: {
  accountId: string;
  path: string;
  label: string;
}) {
  const mutation = useCardMutation(accountId, path, "delete");
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="mt-2">
      <button
        type="button"
        className="text-sm text-gray-400 underline"
        disabled={mutation.isPending}
        onClick={async () => {
          if (
            !window.confirm(
              "Usunąć wyłącznie błędny opis/powiązanie? Transakcje i saldo księgi pozostaną bez zmian. Rozliczona historia planu jest chroniona.",
            )
          )
            return;
          setError(null);
          try {
            await mutation.mutateAsync(undefined);
          } catch (reason) {
            setError(loanApiErrorMessage(reason));
          }
        }}
      >
        {label}
      </button>
      {error ? (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

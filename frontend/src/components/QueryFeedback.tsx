import type { ReactNode } from "react";

type QueryFeedbackProps = {
  loading?: boolean;
  error?: boolean;
  errorMessage: string;
  onRetry?: () => unknown;
  children: ReactNode;
};

export function QueryFeedback({
  loading,
  error,
  errorMessage,
  onRetry,
  children,
}: QueryFeedbackProps) {
  if (error) {
    return (
      <div role="alert" className="py-3 text-sm text-red-300">
        <p>{errorMessage}</p>
        {onRetry && (
          <button
            type="button"
            className="btn-secondary mt-3"
            onClick={() => void onRetry()}
          >
            Spróbuj ponownie
          </button>
        )}
      </div>
    );
  }
  if (loading)
    return (
      <p role="status" className="py-3 text-sm text-gray-400">
        Ładowanie danych…
      </p>
    );
  return <>{children}</>;
}

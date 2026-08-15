import { buildCategoryTree, type CategorySummary } from "../../api/finance";
import { formatPLN } from "../../lib/format";

type CategorySpendTreeProps = {
  summary?: CategorySummary;
  loading: boolean;
  error: boolean;
  title: string;
};

export function CategorySpendTree({
  summary,
  loading,
  error,
  title,
}: CategorySpendTreeProps) {
  const groups = summary ? buildCategoryTree(summary) : [];
  const period = summary
    ? new Intl.DateTimeFormat("pl-PL", {
        month: "long",
        year: "numeric",
      }).format(new Date(summary.year, summary.month - 1, 1))
    : null;

  return (
    <section className="card">
      <div className="mb-4 flex items-start justify-between gap-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {period ? (
          <p className="shrink-0 text-sm capitalize text-gray-400">{period}</p>
        ) : null}
      </div>
      {loading ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : error ? (
        <p className="py-4 text-sm text-red-400">
          Nie udało się pobrać wydatków według kategorii.
        </p>
      ) : !summary || groups.length === 0 ? (
        <p className="py-4 text-sm text-gray-500">
          Brak wydatków skategoryzowanych w tym miesiącu.
        </p>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.category_id}>
              <div className="flex items-center justify-between gap-4 text-sm font-medium text-gray-200">
                <span>{group.name}</span>
                <span className="shrink-0 font-mono">
                  {formatPLN(group.total_pln)} PLN
                </span>
              </div>
              {group.children.length > 0 ? (
                <div className="mt-1 space-y-1 border-l border-gray-700 pl-3">
                  {group.children.map((category) => (
                    <div
                      key={category.category_id}
                      className="flex items-center justify-between gap-4 text-sm text-gray-400"
                    >
                      <span>{category.name}</span>
                      <span className="shrink-0 font-mono">
                        {formatPLN(category.total_pln)} PLN
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

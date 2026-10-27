import {
  buildCategoryTree,
  type CategorySummary,
  type CategorySummaryNode,
} from "../../api/finance";
import { formatPLN } from "../../lib/format";
import { financePeriodSearch } from "./useFinancePeriod";

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
  const tree = summary?.tree;
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
      ) : !summary || (!tree?.length && groups.length === 0) ? (
        <p className="py-4 text-sm text-gray-500">
          Brak wydatków skategoryzowanych w tym miesiącu.
        </p>
      ) : (
        <div className="space-y-3">
          {tree?.length
            ? tree.map((node) => (
                <SpendNode
                  key={node.category_id}
                  node={node}
                  summary={summary}
                />
              ))
            : groups.map((group) => (
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

function SpendNode({
  node,
  summary,
}: {
  node: CategorySummaryNode;
  summary: CategorySummary;
}) {
  const month = String(summary.month).padStart(2, "0");
  const lastDay = new Date(summary.year, summary.month, 0).getDate();
  const href = `/finances/transactions${financePeriodSearch({ month: summary.month, year: summary.year })}&category_id=${encodeURIComponent(node.category_id)}&include_descendants=true&budget_accounts_only=true&date_from=${summary.year}-${month}-01&date_to=${summary.year}-${month}-${lastDay}`;

  return (
    <div>
      <div className="flex min-w-0 items-start justify-between gap-4 text-sm text-gray-200">
        <div className="min-w-0">
          <a
            className="break-words font-medium [overflow-wrap:anywhere]"
            href={href}
          >
            {node.name}
          </a>
          {!node.is_active ? (
            <span className="ml-2 text-xs text-gray-500">archiwalna</span>
          ) : null}
          <p className="text-xs text-gray-500">
            w tym bezpośrednio: {formatPLN(node.direct_total_pln)} PLN
          </p>
        </div>
        <span className="shrink-0 font-mono">
          {formatPLN(node.total_pln)} PLN
        </span>
      </div>
      {node.children.length ? (
        <div className="mt-1 space-y-2 border-l border-gray-700 pl-3">
          {node.children.map((child) => (
            <SpendNode key={child.category_id} node={child} summary={summary} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

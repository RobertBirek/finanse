import {
  buildCategoryTree,
  type CategorySummary,
  type CategorySummaryNode,
  type Category,
  type CategorySpend,
} from "../../api/finance";
import { categoryColorMap, entityColor } from "../../lib/financeColors";
import { formatPLN } from "../../lib/format";
import { financePeriodSearch } from "./useFinancePeriod";

type CategorySpendTreeProps = {
  summary?: CategorySummary;
  loading: boolean;
  error: boolean;
  title: string;
  categories?: Category[];
};

export function CategorySpendTree({
  summary,
  loading,
  error,
  title,
  categories = [],
}: CategorySpendTreeProps) {
  const groups = summary ? buildCategoryTree(summary) : [];
  const tree = summary?.tree;
  const colors = categoryColorMap(categories);
  const amounts: number[] = [];
  const pending: Array<CategorySpend & { children?: CategorySpend[] }> = [
    ...(tree?.length ? tree : groups),
  ];
  while (pending.length) {
    const node = pending.pop()!;
    amounts.push(Math.abs(node.total_pln));
    pending.push(...(node.children ?? []));
  }
  const maximum = Math.max(1, ...amounts);
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
                  colors={colors}
                  maximum={maximum}
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
                  <SpendBar
                    id={group.category_id}
                    name={group.name}
                    amount={group.total_pln}
                    maximum={maximum}
                    color={
                      colors.get(group.category_id) ??
                      entityColor(group.category_id)
                    }
                  />
                  {group.children.length > 0 ? (
                    <div className="mt-1 space-y-1 border-l border-gray-700 pl-3">
                      {group.children.map((category) => (
                        <div key={category.category_id}>
                          <div className="flex items-center justify-between gap-4 text-sm text-gray-400">
                            <span>{category.name}</span>
                            <span className="shrink-0 font-mono">
                              {formatPLN(category.total_pln)} PLN
                            </span>
                          </div>
                          <SpendBar
                            id={category.category_id}
                            name={category.name}
                            amount={category.total_pln}
                            maximum={maximum}
                            color={
                              colors.get(category.category_id) ??
                              colors.get(group.category_id) ??
                              entityColor(group.category_id)
                            }
                          />
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
  colors,
  maximum,
}: {
  node: CategorySummaryNode;
  summary: CategorySummary;
  colors: Map<string, string>;
  maximum: number;
}) {
  const month = String(summary.month).padStart(2, "0");
  const lastDay = new Date(summary.year, summary.month, 0).getDate();
  const href = `/finances/transactions${financePeriodSearch({ month: summary.month, year: summary.year })}&category_id=${encodeURIComponent(node.category_id)}&include_descendants=true&budget_accounts_only=true&date_from=${summary.year}-${month}-01&date_to=${summary.year}-${month}-${lastDay}`;
  const color = colors.get(node.category_id) ?? entityColor(node.category_id);

  return (
    <div>
      <div className="flex min-w-0 items-start justify-between gap-4 text-sm text-gray-200">
        <div className="min-w-0">
          <a
            className="break-words font-medium [overflow-wrap:anywhere]"
            href={href}
          >
            <span
              aria-hidden="true"
              className="mr-2 inline-block h-3 w-3 rounded-full border border-gray-500/40"
              style={{ backgroundColor: color }}
            />
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
      <SpendBar
        id={node.category_id}
        name={node.name}
        amount={node.total_pln}
        maximum={maximum}
        color={color}
      />
      {node.children.length ? (
        <div className="mt-1 space-y-2 border-l border-gray-700 pl-3">
          {node.children.map((child) => (
            <SpendNode
              key={child.category_id}
              node={child}
              summary={summary}
              colors={colors}
              maximum={maximum}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SpendBar({
  id,
  name,
  amount,
  maximum,
  color,
}: {
  id: string;
  name: string;
  amount: number;
  maximum: number;
  color: string;
}) {
  return (
    <div
      className="my-2 h-1.5 overflow-hidden rounded-full bg-gray-500/10"
      title={`${name}: ${formatPLN(amount)} PLN`}
    >
      <span
        role="img"
        aria-label={`Wydatki: ${name}`}
        data-category-id={id}
        className="block h-full rounded-full border border-black/10"
        style={{
          backgroundColor: color,
          width: `${Math.min(100, (Math.abs(amount) / maximum) * 100)}%`,
        }}
      />
    </div>
  );
}

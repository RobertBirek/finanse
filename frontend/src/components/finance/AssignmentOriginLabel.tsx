import type { AssignmentOrigin } from "../../api/categorization";

export function AssignmentOriginLabel({
  origin,
}: {
  origin?: AssignmentOrigin | null;
}) {
  if (!origin) return null;
  return (
    <p
      className="text-xs text-gray-400 [overflow-wrap:anywhere]"
      title={
        origin.origin === "approved_rule"
          ? `${origin.display_description ?? ""} → ${origin.target_path ?? ""} · wersja ${origin.rule_version}`
          : undefined
      }
    >
      {origin.origin === "approved_rule"
        ? "Kategoria z zatwierdzonej reguły"
        : "Ręcznie zatwierdzona kategoria"}
    </p>
  );
}

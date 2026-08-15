import { formatPLN } from "../../lib/format";

type SummaryCardProps = {
  label: string;
  amount: number;
  tone: "income" | "expense" | "net";
};

export function SummaryCard({ label, amount, tone }: SummaryCardProps) {
  const color =
    tone === "income" || (tone === "net" && amount >= 0)
      ? "text-green-400"
      : "text-red-400";

  return (
    <div className="card">
      <p className="mb-1 text-xs text-gray-400">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{formatPLN(amount)} PLN</p>
    </div>
  );
}

type CashflowMetricProps = {
  label: string;
  amount: number;
  neutral?: boolean;
};

export function CashflowMetric({
  label,
  amount,
  neutral = false,
}: CashflowMetricProps) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p
        className={`mt-1 text-xl font-bold ${neutral ? "text-white" : amount >= 0 ? "text-green-400" : "text-red-400"}`}
      >
        {formatPLN(amount)} PLN
      </p>
    </div>
  );
}

import type { Account } from "../../../api/finance";
import type { Loan } from "../../../api/loans";
import type { ScheduleTargetData } from "../../../api/loanScheduleImports";

export function validScheduleTarget(
  value: ScheduleTargetData,
  loans: Loan[],
  accounts: Account[],
) {
  const activePln = (ids: string[]) =>
    new Set(ids).size === 2 &&
    ids.every((id) =>
      accounts.some(
        (a) =>
          a.id === id &&
          a.is_active &&
          a.currency === "PLN" &&
          a.type !== "credit_card" &&
          !a.credit_card,
      ),
    );
  if (value.loan_id) {
    const loan = loans.find((l) => l.id === value.loan_id && l.is_active);
    return !!loan && activePln([loan.account_id, loan.payment_account_id]);
  }
  const n = value.new_loan;
  if (
    !n?.name.trim() ||
    !n.account_id ||
    !n.payment_account_id ||
    n.account_id === n.payment_account_id
  )
    return false;
  return activePln([n.account_id, n.payment_account_id]);
}

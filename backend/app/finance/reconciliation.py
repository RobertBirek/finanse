from dataclasses import dataclass


class ReconciliationError(ValueError):
    """Raised when an import is not reconciled account by account."""


@dataclass(frozen=True)
class SourceBalance:
    actual_id: str
    name: str
    currency: str
    is_budget_account: bool
    amount: int


@dataclass(frozen=True)
class AccountReconciliation:
    actual: SourceBalance | None
    pa: SourceBalance | None
    difference: int | None

    @property
    def is_reconciled(self) -> bool:
        return (
            self.actual is not None
            and self.pa is not None
            and self.actual.currency == self.pa.currency
            and self.actual.is_budget_account == self.pa.is_budget_account
            and self.difference == 0
        )

    def to_dict(self) -> dict[str, str | int | bool | None]:
        source = self.actual or self.pa
        return {
            "actual_id": source.actual_id if source is not None else None,
            "actual_name": self.actual.name if self.actual is not None else None,
            "pa_name": self.pa.name if self.pa is not None else None,
            "currency": source.currency if source is not None else None,
            "is_budget_account": source.is_budget_account if source is not None else None,
            "pa_currency": self.pa.currency if self.pa is not None else None,
            "pa_is_budget_account": self.pa.is_budget_account if self.pa is not None else None,
            "actual_amount": self.actual.amount if self.actual is not None else None,
            "pa_amount": self.pa.amount if self.pa is not None else None,
            "difference": self.difference,
            "is_reconciled": self.is_reconciled,
        }

    def to_text(self) -> str:
        source = self.actual or self.pa
        if source is None:
            return ""
        budget = "budget" if source.is_budget_account else "offbudget"
        actual_amount = self.actual.amount if self.actual is not None else "-"
        pa_amount = self.pa.amount if self.pa is not None else "-"
        difference = self.difference if self.difference is not None else "-"
        status = "OK" if self.is_reconciled else "MISMATCH"
        return (
            f"{source.name} | {source.currency} | {budget} | Actual {actual_amount} | "
            f"PA {pa_amount} | diff {difference} | {status}"
        )


@dataclass(frozen=True)
class CategoryBalance:
    actual_id: str
    name: str
    type: str
    amount_pln: int


@dataclass(frozen=True)
class CategoryReconciliation:
    actual: CategoryBalance | None
    pa: CategoryBalance | None
    difference: int | None

    @property
    def is_reconciled(self) -> bool:
        return (
            self.actual is not None
            and self.pa is not None
            and self.actual.type == self.pa.type
            and self.difference == 0
        )

    def to_dict(self) -> dict[str, str | int | bool | None]:
        source = self.actual or self.pa
        return {
            "actual_id": source.actual_id if source is not None else None,
            "actual_name": self.actual.name if self.actual is not None else None,
            "pa_name": self.pa.name if self.pa is not None else None,
            "type": source.type if source is not None else None,
            "pa_type": self.pa.type if self.pa is not None else None,
            "actual_amount_pln": self.actual.amount_pln if self.actual is not None else None,
            "pa_amount_pln": self.pa.amount_pln if self.pa is not None else None,
            "difference": self.difference,
            "is_reconciled": self.is_reconciled,
        }

    def to_text(self) -> str:
        source = self.actual or self.pa
        if source is None:
            return ""
        actual_amount = self.actual.amount_pln if self.actual is not None else "-"
        pa_amount = self.pa.amount_pln if self.pa is not None else "-"
        difference = self.difference if self.difference is not None else "-"
        status = "OK" if self.is_reconciled else "MISMATCH"
        return (
            f"{source.name} | {source.type} | Actual {actual_amount} | PA {pa_amount} | "
            f"diff {difference} | {status}"
        )


@dataclass(frozen=True)
class ReconciliationReport:
    accounts: tuple[AccountReconciliation, ...]
    categories: tuple[CategoryReconciliation, ...] = ()
    category_groups: tuple[CategoryReconciliation, ...] = ()
    import_errors: tuple[str, ...] = ()

    @property
    def is_reconciled(self) -> bool:
        return (
            not self.import_errors
            and all(account.is_reconciled for account in self.accounts)
            and all(category.is_reconciled for category in self.categories)
            and all(group.is_reconciled for group in self.category_groups)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "is_reconciled": self.is_reconciled,
            "accounts": [account.to_dict() for account in self.accounts],
            "categories": [category.to_dict() for category in self.categories],
            "category_groups": [group.to_dict() for group in self.category_groups],
            "import_errors": list(self.import_errors),
        }

    def to_text(self) -> str:
        lines = [account.to_text() for account in self.accounts]
        if self.categories:
            lines.extend(["Categories:", *(category.to_text() for category in self.categories)])
        if self.category_groups:
            lines.extend(["Category groups:", *(group.to_text() for group in self.category_groups)])
        if self.import_errors:
            lines.extend(["Import errors:", *(f"  [E] {error}" for error in self.import_errors)])
        return "\n".join(lines)


def reconcile_account_balances(
    expected: dict[str, SourceBalance], actual: dict[str, SourceBalance]
) -> ReconciliationReport:
    account_ids = set(expected) | set(actual)
    accounts = []
    for actual_id in account_ids:
        expected_balance = expected.get(actual_id)
        actual_balance = actual.get(actual_id)
        difference = (
            expected_balance.amount - actual_balance.amount
            if expected_balance is not None and actual_balance is not None
            else None
        )
        accounts.append(
            AccountReconciliation(
                actual=expected_balance,
                pa=actual_balance,
                difference=difference,
            )
        )

    def sort_key(account: AccountReconciliation) -> tuple[str, str]:
        source = account.actual or account.pa
        if source is None:
            return ("", "")
        return (source.name.casefold(), source.actual_id)

    accounts.sort(key=sort_key)
    return ReconciliationReport(accounts=tuple(accounts))


def reconcile_category_balances(
    expected: dict[str, CategoryBalance], actual: dict[str, CategoryBalance]
) -> tuple[CategoryReconciliation, ...]:
    category_ids = set(expected) | set(actual)
    categories = []
    for actual_id in category_ids:
        expected_balance = expected.get(actual_id)
        actual_balance = actual.get(actual_id)
        difference = (
            expected_balance.amount_pln - actual_balance.amount_pln
            if expected_balance is not None and actual_balance is not None
            else None
        )
        categories.append(
            CategoryReconciliation(
                actual=expected_balance,
                pa=actual_balance,
                difference=difference,
            )
        )

    def sort_key(category: CategoryReconciliation) -> tuple[str, str]:
        source = category.actual or category.pa
        if source is None:
            return ("", "")
        return (source.name.casefold(), source.actual_id)

    categories.sort(key=sort_key)
    return tuple(categories)


def require_reconciled(report: ReconciliationReport) -> None:
    if not report.is_reconciled:
        raise ReconciliationError("Actual import is not reconciled")

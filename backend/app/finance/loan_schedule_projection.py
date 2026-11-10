"""Single active-plan predicate; NULL preserves the entire legacy plan."""

from sqlalchemy.sql.elements import ColumnElement

from app.finance.models import LoanInstallment


def active_installment_predicate() -> ColumnElement[bool]:
    return LoanInstallment.superseded_by_revision_id.is_(None)

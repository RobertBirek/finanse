"""Compatibility facade for routers, AI tools, imports and integrations.

Implementation modules depend on focused peers, never on this facade.
Keep public entrypoints here while their responsibilities live in small modules.
"""

from app.finance import (
    budgets,
    cashflow,
    dates,
    entities,
    ledger_validation,
    loans,
    queries,
    reporting,
    transactions,
)

get_account = queries.get_account
get_accounts = queries.get_accounts
get_transaction = queries.get_transaction
get_transactions = queries.get_transactions
search_transactions = queries.search_transactions

SUPPORTED_CURRENCIES = entities.SUPPORTED_CURRENCIES
create_account = entities.create_account
update_account = entities.update_account
delete_account = entities.delete_account
create_category = entities.create_category
get_categories = entities.get_categories
update_category = entities.update_category
delete_category = entities.delete_category
_validate_category_parent = entities._validate_category_parent
_validate_posting_sum = ledger_validation._validate_posting_sum
_validate_transaction_postings = ledger_validation._validate_transaction_postings

create_transaction = transactions.create_transaction
create_exchange_transaction = transactions.create_exchange_transaction
update_transaction = transactions.update_transaction
delete_transaction = transactions.delete_transaction

create_loan = loans.create_loan
update_loan = loans.update_loan
get_loan = loans.get_loan
get_loans = loans.get_loans
create_loan_installment = loans.create_loan_installment
update_loan_installment = loans.update_loan_installment
delete_loan_installment = loans.delete_loan_installment
link_loan_payment = loans.link_loan_payment
unlink_loan_payment = loans.unlink_loan_payment
get_loan_payment_candidates = loans.get_loan_payment_candidates

get_financial_summary = reporting.get_financial_summary
get_category_summary = reporting.get_category_summary

create_budget = budgets.create_budget
get_budgets = budgets.get_budgets
update_budget = budgets.update_budget
delete_budget = budgets.delete_budget
get_budget_status = budgets.get_budget_status

get_or_create_finance_settings = cashflow.get_or_create_finance_settings
update_finance_settings = cashflow.update_finance_settings
create_scheduled_item = cashflow.create_scheduled_item
get_scheduled_items = cashflow.get_scheduled_items
update_scheduled_item = cashflow.update_scheduled_item
delete_scheduled_item = cashflow.delete_scheduled_item
get_cashflow_forecast = cashflow.get_cashflow_forecast
confirm_scheduled_item = cashflow.confirm_scheduled_item

# Retain helper imports for existing integrations; patch implementation owners in tests.
_local_today = dates._local_today
_month_bounds = dates._month_bounds
_add_month = dates._add_month
_payday_bounds = dates._payday_bounds

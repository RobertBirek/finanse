"""Exact gross/discount/net aggregation, independent from storage and authority."""

import uuid
from collections import defaultdict

from app.config import settings
from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.categorization_schemas import CategorizationPart
from app.finance.receipt_schemas import (
    ReceiptBody,
    ReceiptCalculation,
    ReceiptLineNet,
    ReceiptProblem,
)


def calculate_receipt(body: ReceiptBody, *, expected_total_minor: int) -> ReceiptCalculation:
    problems: list[ReceiptProblem] = []
    shares: dict[uuid.UUID, int] = defaultdict(int)
    unknown: set[uuid.UUID] = set()

    def issue(
        code: str, message: str, *, line: uuid.UUID | None = None, discount: uuid.UUID | None = None
    ) -> None:
        problems.append(
            ReceiptProblem(code=code, message=message, line_key=line, discount_key=discount)
        )

    for d in body.discounts:
        refs = {s.line_key for s in d.shares}
        valid = (
            d.amount_minor is not None
            and bool(d.shares)
            and all(s.amount_minor is not None for s in d.shares)
        )
        if not d.name.strip():
            issue("missing_name", "Podaj nazwę rabatu.", discount=d.discount_key)
        if not valid or sum(s.amount_minor or 0 for s in d.shares) != d.amount_minor:
            issue(
                "discount_shares",
                "Uzupełnij udziały rabatu zgodnie z jego kwotą.",
                discount=d.discount_key,
            )
            unknown.update(refs or {r.line_key for r in body.lines})
        for s in d.shares:
            if s.amount_minor is not None:
                shares[s.line_key] += s.amount_minor
    parts: dict[uuid.UUID, int] = defaultdict(int)
    nets = []
    for r in body.lines:
        if not r.name.strip():
            issue("missing_name", "Podaj nazwę produktu.", line=r.line_key)
        if r.amount_minor is None:
            issue("missing_amount", "Uzupełnij kwotę produktu.", line=r.line_key)
        net = (
            r.amount_minor - shares[r.line_key]
            if r.amount_minor is not None and r.line_key not in unknown
            else None
        )
        if net is not None and net < 0:
            issue("negative_net", "Rabaty przekraczają kwotę produktu.", line=r.line_key)
        if net is not None and abs(net) > MAX_SAFE_MINOR:
            issue("amount_out_of_range", "Kwota przekracza dozwolony zakres.", line=r.line_key)
            net = None
        if net is not None and net > 0:
            if r.category_id is None:
                issue("missing_category", "Wybierz kategorię produktu.", line=r.line_key)
            else:
                parts[r.category_id] += net
        nets.append(ReceiptLineNet(line_key=r.line_key, net_minor=net))
    if not body.lines:
        issue("no_lines", "Dodaj pozycje paragonu.")
    total = (
        sum(n.net_minor or 0 for n in nets)
        if nets and all(n.net_minor is not None for n in nets)
        else None
    )
    difference = total - expected_total_minor if total is not None else None
    if difference not in (None, 0):
        issue(
            "total_mismatch", "Suma pozycji po rabatach musi zgadzać się z paragonem co do grosza."
        )
    if total is not None and (
        abs(total) > MAX_SAFE_MINOR or any(v > MAX_SAFE_MINOR for v in parts.values())
    ):
        issue("amount_out_of_range", "Suma przekracza dozwolony zakres.")
        total, difference = None, None
    if difference is not None and abs(difference) > MAX_SAFE_MINOR:
        issue("amount_out_of_range", "Różnica przekracza dozwolony zakres.")
        difference = None
    if len(parts) > settings.FINANCE_CATEGORY_SPLIT_MAX_PARTS:
        issue("too_many_parts", "Zbyt wiele kategorii w podziale.")
    fatal = any(
        p.code in {"negative_net", "amount_out_of_range", "discount_shares", "too_many_parts"}
        for p in problems
    )
    return ReceiptCalculation(
        line_nets=nets,
        net_total_minor=total,
        difference_minor=difference,
        parts=[]
        if fatal
        else [
            CategorizationPart(category_id=k, amount_minor=v)
            for k, v in sorted(parts.items(), key=lambda item: str(item[0]))
        ],
        problems=problems,
    )

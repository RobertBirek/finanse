"""Explicit statement-header confirmation adapter; no accounts, balances or postings are written."""

import hashlib
import json
import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from app.finance.credit_card_schemas import StatementCreate
from app.finance.imports.contracts import MAX_MINOR_UNITS, ParsedStatement
from app.finance.imports.errors import ImportError


class CardHeaderDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    debt_pln: int = Field(strict=True, ge=0, le=MAX_MINOR_UNITS)
    minimum_pln: int = Field(strict=True, ge=0, le=MAX_MINOR_UNITS)
    debt_definition_confirmed: StrictBool


def validate_card_header(parsed: ParsedStatement, decision: CardHeaderDecision) -> StatementCreate:
    header = parsed.card_header
    if (
        parsed.bank != "velo"
        or parsed.layout != "velo_card_v1"
        or parsed.currency != "PLN"
        or header is None
    ):
        raise ImportError(
            "card_header_unsupported", "Brak rozpoznanych metadanych okresu karty.", 422
        )
    if not decision.debt_definition_confirmed or header.get("debt_definition") != "current_cycle":
        raise ImportError(
            "card_debt_definition_unconfirmed",
            "Potwierdź znaczenie zadłużenia z nagłówka, nie limit ani przyszłe raty.",
            422,
        )
    matches = (
        decision.period_start == parsed.period_start
        and decision.period_end == parsed.period_end
        and decision.due_date.isoformat() == header.get("due_date")
        and type(header.get("cycle_debt_pln")) is int
        and decision.debt_pln == header.get("cycle_debt_pln")
        and type(header.get("minimum_pln")) is int
        and decision.minimum_pln == header.get("minimum_pln")
    )
    if not matches:
        raise ImportError(
            "card_header_confirmation_mismatch",
            "Potwierdzenie nie odpowiada kompletnym danym źródłowym.",
            422,
        )
    payload = {
        "parsed": parsed.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        return StatementCreate(
            request_id=uuid.uuid5(uuid.NAMESPACE_URL, "bank-import:" + digest),
            period_start=decision.period_start,
            period_end=decision.period_end,
            due_date=decision.due_date,
            debt_pln=decision.debt_pln,
            minimum_pln=decision.minimum_pln,
            source_reference="bank-import:" + digest,
        )
    except ValidationError as error:
        raise ImportError(
            "card_header_invalid", "Nieprawidłowy okres, termin lub kwoty wyciągu karty.", 422
        ) from error

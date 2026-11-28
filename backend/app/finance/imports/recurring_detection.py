"""Pure, conservative evidence analysis for *new* recurring-expense schedule proposals.

This module deliberately knows nothing about persisted schedules.  A caller must
perform any existing-schedule check separately; similarity of an amount or
description is never evidence that a duplicate is absent.
"""

from __future__ import annotations

import unicodedata
import uuid
from calendar import monthrange
from datetime import date
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

Currency = Literal["PLN", "EUR", "USD"]
ObservationSource = Literal["actual", "bank_import"]
EconomicIdentityState = Literal["canonical", "unknown"]
ProposalStatus = Literal["proposed", "blocked", "uncertain"]
Cadence = Literal["monthly", "annual"]
AmountKind = Literal["stable", "variable"]
SAFE_EVIDENCE_LIMIT = 5
DAY_TOLERANCE = 3


class VerifiedExpenseObservation(BaseModel):
    """A verified expense with a caller-attested economic identity.

    ``canonical`` attests that upstream reconciliation has assigned one global
    economic-event identity across actual history and bank imports. ``unknown``
    is not eligible for a recurrence proposal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: uuid.UUID
    account_id: uuid.UUID
    currency: Currency
    source: ObservationSource
    strong_identity: str
    occurred_on: date
    description: str
    amount_minor: StrictInt
    economic_identity: str | None
    economic_identity_state: EconomicIdentityState


class RecurrenceEvidence(BaseModel):
    """Bounded structured provenance, deliberately excluding untrusted text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strong_identity: str
    economic_identity: str | None
    source: ObservationSource
    occurred_on: date
    amount_minor: StrictInt
    currency: Currency


class NewScheduleProposal(BaseModel):
    """A candidate only; it makes no claim about persisted schedules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: Literal["new_schedule"] = "new_schedule"
    merchant: str
    frequency: Cadence
    amount_kind: AmountKind
    amount_minor: StrictInt | None
    currency: Currency
    formal_deadline: None = None


class RecurrenceAnalysis(BaseModel):
    """The outcome is explicit about blocked and uncertain evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProposalStatus
    reason: str | None = None
    proposal: NewScheduleProposal | None = None
    evidence: tuple[RecurrenceEvidence, ...] = Field(default_factory=tuple)


def _merchant_key(description: str) -> str:
    """Normalize presentation only; variable tokens are intentionally retained."""
    return " ".join(unicodedata.normalize("NFKC", description).lower().split())


def _evidence(observations: list[VerifiedExpenseObservation]) -> tuple[RecurrenceEvidence, ...]:
    return tuple(
        RecurrenceEvidence(
            strong_identity=observation.strong_identity,
            economic_identity=observation.economic_identity,
            source=observation.source,
            occurred_on=observation.occurred_on,
            amount_minor=observation.amount_minor,
            currency=observation.currency,
        )
        for observation in sorted(observations, key=lambda item: item.occurred_on)[
            -SAFE_EVIDENCE_LIMIT:
        ]
    )


def _outcome(
    status: Literal["blocked", "uncertain"],
    reason: str,
    observations: list[VerifiedExpenseObservation],
) -> RecurrenceAnalysis:
    return RecurrenceAnalysis(status=status, reason=reason, evidence=_evidence(observations))


def _consecutive_months(ordered: list[VerifiedExpenseObservation]) -> bool:
    return all(
        later.occurred_on.year * 12 + later.occurred_on.month
        == earlier.occurred_on.year * 12 + earlier.occurred_on.month + 1
        and abs(later.occurred_on.day - earlier.occurred_on.day) <= DAY_TOLERANCE
        for earlier, later in pairwise(ordered)
    )


def _consecutive_years_same_month(ordered: list[VerifiedExpenseObservation]) -> bool:
    return all(
        abs(
            (
                later.occurred_on
                - date(
                    earlier.occurred_on.year + 1,
                    earlier.occurred_on.month,
                    min(
                        earlier.occurred_on.day,
                        monthrange(
                            earlier.occurred_on.year + 1,
                            earlier.occurred_on.month,
                        )[1],
                    ),
                )
            ).days
        )
        <= DAY_TOLERANCE
        for earlier, later in pairwise(ordered)
    )


def analyze_new_recurring_schedule(
    current: VerifiedExpenseObservation,
    historical: list[VerifiedExpenseObservation],
) -> RecurrenceAnalysis:
    """Analyze one current bank expense against owner/account/currency-scoped history.

    The caller must attest distinct canonical economic identities after upstream
    reconciliation. This function does not itself deduplicate source rows or
    determine whether a schedule already exists; it never queries or creates
    schedules.
    """
    observations = [*historical, current]
    if current.source != "bank_import" or any(item.amount_minor >= 0 for item in observations):
        return _outcome("uncertain", "scope_or_current_source_uncertain", observations)
    if any(not item.strong_identity.strip() for item in observations):
        return _outcome("uncertain", "identity_uncertain", observations)
    if len({item.strong_identity for item in observations}) != len(observations):
        return _outcome("uncertain", "identity_uncertain", observations)
    if any(
        item.owner_id != current.owner_id
        or item.account_id != current.account_id
        or item.currency != current.currency
        for item in observations
    ):
        return _outcome("uncertain", "scope_or_current_source_uncertain", observations)
    if any(item.occurred_on > current.occurred_on for item in historical):
        return _outcome("uncertain", "current_not_latest", observations)
    if any(
        item.economic_identity_state != "canonical" or not item.economic_identity
        for item in observations
    ):
        return _outcome("uncertain", "economic_identity_uncertain", observations)
    economic_identities = [item.economic_identity for item in observations]
    if len(set(economic_identities)) != len(economic_identities):
        return _outcome("uncertain", "economic_identity_collision", observations)

    merchant = _merchant_key(current.description)
    if not merchant:
        return _outcome("uncertain", "merchant_uncertain", observations)
    matching = [item for item in observations if _merchant_key(item.description) == merchant]
    if len(matching) < 3:
        return _outcome("blocked", "insufficient_verified_observations", matching)

    ordered = sorted(matching, key=lambda item: item.occurred_on)
    if len({item.occurred_on for item in ordered}) != len(ordered):
        return _outcome("uncertain", "chronology_uncertain", ordered)
    gaps = [(later.occurred_on - earlier.occurred_on).days for earlier, later in pairwise(ordered)]
    if _consecutive_months(ordered):
        frequency: Cadence = "monthly"
    elif _consecutive_years_same_month(ordered):
        frequency = "annual"
    elif gaps and all(gap == 28 for gap in gaps):
        return _outcome("uncertain", "cadence_ambiguous_four_weekly", ordered)
    else:
        return _outcome("blocked", "unsupported_cadence", ordered)

    amounts = {item.amount_minor for item in ordered}
    amount_kind: AmountKind = "stable" if len(amounts) == 1 else "variable"
    proposal = NewScheduleProposal(
        merchant=merchant,
        frequency=frequency,
        amount_kind=amount_kind,
        amount_minor=ordered[-1].amount_minor if amount_kind == "stable" else None,
        currency=current.currency,
    )
    return RecurrenceAnalysis(
        status="proposed",
        proposal=proposal,
        evidence=_evidence(ordered),
    )

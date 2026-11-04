"""One lock-free MVCC observation shared by creation-only rule/AI enrollment."""

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import CategorizationError
from app.finance.rule_models import (
    TransactionCategorizationRule as Rule,
)
from app.finance.rule_models import (
    TransactionCategorizationSettings as Rules,
)
from app.finance.rule_policy import normalize_rule_description
from app.finance.suggestion_config import get_suggestion_config
from app.finance.suggestion_models import (
    CategorizationLlmPolicy as Server,
)
from app.finance.suggestion_models import (
    CategorizationSuggestionSettings as Consent,
)


@dataclass(frozen=True)
class CreationObservation:
    marker_id: uuid.UUID | None = None
    settings_version: int = 0
    rules_enabled: bool = False
    rule_candidates: tuple[tuple[uuid.UUID, int], ...] = ()
    user_enabled: bool = False
    user_epoch: int = 0
    server_enabled: bool = False
    server_epoch: int = 0
    fingerprint: str | None = None
    configuration_ready: bool = False


async def observe_creation_policy(
    db: AsyncSession, owner: uuid.UUID, description: str
) -> CreationObservation:
    try:
        normalized = normalize_rule_description(description)
    except CategorizationError:
        normalized = ""
    # Constant anchor keeps missing optional rows visible; do not infer a bind type
    # from asyncpg's UUID subclass when this is called with a freshly loaded job.
    anchor = select(literal(1).label("anchor")).subquery()
    rows = (
        await db.execute(
            select(Rules, Rule, Consent, Server)
            .select_from(anchor)
            .outerjoin(Rules, Rules.user_id == owner)
            .outerjoin(
                Rule,
                and_(
                    Rule.user_id == owner,
                    Rule.state == "active",
                    Rule.normalized_description_exact == normalized,
                ),
            )
            .outerjoin(Consent, Consent.user_id == owner)
            .outerjoin(Server, Server.id == 1)
            .execution_options(populate_existing=True)
        )
    ).all()
    policy, _, consent, server = rows[0]
    config = get_suggestion_config(settings)
    current = bool(
        config
        and server
        and server.enabled
        and server.configuration_fingerprint == config.fingerprint
        and consent
        and consent.enabled
        and consent.accepted_server_epoch == server.epoch
        and consent.accepted_configuration_fingerprint == config.fingerprint
    )
    return CreationObservation(
        marker_id=policy.uncategorized_category_id if policy else None,
        settings_version=policy.version if policy else 0,
        rules_enabled=bool(policy and policy.rules_enabled),
        rule_candidates=tuple((r.id, r.version) for _, r, _, _ in rows if r is not None),
        user_enabled=bool(consent and consent.enabled),
        user_epoch=consent.version if consent else 0,
        server_enabled=bool(server and server.enabled),
        server_epoch=server.epoch if server else 0,
        fingerprint=config.fingerprint if config else None,
        configuration_ready=current,
    )

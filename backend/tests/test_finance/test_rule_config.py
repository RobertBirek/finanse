import pytest
from pydantic import ValidationError

from app.config import Settings


def test_configured_rule_description_limit_cannot_exceed_database_capacity():
    with pytest.raises(ValidationError):
        Settings(FINANCE_RULE_DESCRIPTION_MAX_CHARS=2001)

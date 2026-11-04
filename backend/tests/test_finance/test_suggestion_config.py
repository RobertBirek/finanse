from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.finance.suggestion_config import get_suggestion_config


def test_config_is_dedicated_failclosed_and_credentials_do_not_define_grant():
    s = Settings(_env_file=None, OPENAI_API_KEY="not-finance", LLM_MODEL="not-finance")
    assert get_suggestion_config(s) is None
    s.FINANCE_SUGGESTIONS_ENABLED = True
    assert get_suggestion_config(s) is None
    s.FINANCE_SUGGESTIONS_PROVIDER = "openai"
    s.FINANCE_SUGGESTIONS_BASE_URL = "https://api.openai.com/v1"
    s.FINANCE_SUGGESTIONS_MODEL = "test-model"
    s.FINANCE_SUGGESTIONS_API_KEY = "test-secret"
    c = get_suggestion_config(s)
    assert c is not None and "test-secret" not in repr(c)
    assert replace(c, api_key="rotated").fingerprint == c.fingerprint
    assert replace(c, daily_call_limit=6).fingerprint != c.fingerprint
    assert replace(c, model="other").fingerprint != c.fingerprint
    s.FINANCE_SUGGESTIONS_BASE_URL = "https://api.openai.com.evil.test/v1"
    assert get_suggestion_config(s) is None


@pytest.mark.parametrize(
    "config",
    [
        {"FINANCE_SUGGESTIONS_DESCRIPTION_MAX_CHARS": 2001},
        {"FINANCE_SUGGESTIONS_MAX_CATEGORIES": 1001},
        {"FINANCE_SUGGESTIONS_EXPLANATION_MAX_CHARS": 2001},
        {"FINANCE_SUGGESTIONS_NEW_CATEGORY_MAX_CHARS": 201},
        {"FINANCE_SUGGESTIONS_LEASE_SECONDS": 40},
        {"FINANCE_SUGGESTIONS_JOB_TIMEOUT_SECONDS": 90},
    ],
)
def test_storage_and_lease_bounds_rejected_at_startup(config):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **config)

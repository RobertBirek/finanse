import hashlib
import hmac
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


class RedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> list[int]: ...


class RateLimitUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int | None
    identifier_hash: str


_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def hash_identifier(identifier: str) -> str:
    pepper = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), b"security:rate-limit:v1", hashlib.sha256
    ).digest()
    return hmac.new(pepper, identifier.encode("utf-8"), hashlib.sha256).hexdigest()


async def check_rate_limit(
    scope: str, identifier: str, maximum: int, window_seconds: int
) -> RateLimitResult:
    identifier_hash = hash_identifier(identifier)
    if settings.ENVIRONMENT != "production":
        return RateLimitResult(allowed=True, retry_after=None, identifier_hash=identifier_hash)

    key = f"security:rate-limit:v1:{scope}:{identifier_hash}"
    try:
        result = get_redis_client().eval(RATE_LIMIT_LUA, 1, key, str(window_seconds))
        count, ttl = await cast(Awaitable[list[int]], result)
    except (OSError, TimeoutError, RedisError) as error:
        raise RateLimitUnavailable from error

    retry_after = max(1, int(ttl))
    return RateLimitResult(
        allowed=int(count) <= maximum,
        retry_after=retry_after if int(count) > maximum else None,
        identifier_hash=identifier_hash,
    )

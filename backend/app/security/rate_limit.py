import hashlib
import hmac
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.audit.service import log_security_event
from app.config import settings
from app.identity.schemas import UserLogin

RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


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


def resolve_trusted_proxy_hosts(hosts: tuple[str, ...]) -> set[str]:
    addresses: set[str] = set()
    for host in hosts:
        try:
            records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            continue
        for _family, _type, _protocol, _canonical_name, sockaddr in records:
            try:
                addresses.add(str(ipaddress.ip_address(sockaddr[0])))
            except ValueError:
                continue
    return addresses


def get_client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    try:
        normalized_peer = str(ipaddress.ip_address(peer))
    except ValueError:
        return peer

    if normalized_peer not in resolve_trusted_proxy_hosts(settings.trusted_proxy_hosts):
        return normalized_peer

    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return normalized_peer

    entries = forwarded_for.split(",")
    try:
        chain = [str(ipaddress.ip_address(entry.strip())) for entry in entries]
    except ValueError:
        return normalized_peer
    if not chain or any(not entry.strip() for entry in entries):
        return normalized_peer
    return chain[0]


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


async def _enforce_rate_limit(
    scope: str,
    identifier: str,
    maximum: int,
    window_seconds: int,
    user_id: Any = None,
) -> None:
    try:
        limit = await check_rate_limit(scope, identifier, maximum, window_seconds)
    except RateLimitUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable"
        )
    if limit.allowed:
        return

    await log_security_event(
        "rate_limited",
        limit.identifier_hash,
        user_id=user_id,
        state={"scope": scope, "identifier_hash": limit.identifier_hash},
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Request limit exceeded",
        headers={"Retry-After": str(limit.retry_after)},
    )


async def limit_login(request: Request, data: UserLogin) -> None:
    await _enforce_rate_limit(
        "login",
        f"{get_client_ip(request)}|{data.email.strip().lower()}",
        settings.LOGIN_RATE_LIMIT,
        settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )


def _authenticated_limit(
    scope: str,
    maximum: Callable[[], int],
    window_seconds: Callable[[], int],
    identifier: Callable[[Any, Request], str],
    current_user_dependency: Callable[..., Any],
) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request, current_user: Annotated[Any, Depends(current_user_dependency)]
    ) -> None:
        await _enforce_rate_limit(
            scope,
            identifier(current_user, request),
            maximum(),
            window_seconds(),
            user_id=current_user.id,
        )

    return dependency


def limit_advisor(current_user_dependency: Callable[..., Any]) -> Callable[..., Awaitable[None]]:
    return _authenticated_limit(
        "advisor",
        lambda: settings.ADVISOR_RATE_LIMIT,
        lambda: settings.ADVISOR_RATE_LIMIT_WINDOW_SECONDS,
        lambda user, _request: str(user.id),
        current_user_dependency,
    )


def limit_upload(current_user_dependency: Callable[..., Any]) -> Callable[..., Awaitable[None]]:
    return _authenticated_limit(
        "upload",
        lambda: settings.UPLOAD_RATE_LIMIT,
        lambda: settings.UPLOAD_RATE_LIMIT_WINDOW_SECONDS,
        lambda user, request: f"{user.id}|{get_client_ip(request)}",
        current_user_dependency,
    )

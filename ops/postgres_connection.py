#!/usr/bin/env python3
"""Validate a password-free PostgreSQL URL and emit PG client connection fields."""

import os
import re
import sys
from urllib.parse import unquote, urlsplit


def fail() -> None:
    print("Invalid PostgreSQL connection URL.", file=sys.stderr)
    raise SystemExit(1)


def valid_component(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value))


url = os.environ.get("POSTGRES_CONNECTION_URL", "")
parsed = urlsplit(url)
if (
    parsed.scheme != "postgresql"
    or parsed.query
    or parsed.fragment
    or parsed.password is not None
):
    fail()

port = 0
try:
    port = parsed.port or 5432
except ValueError:
    fail()

username = unquote(parsed.username or "")
hostname = unquote(parsed.hostname or "")
database = unquote(parsed.path[1:]) if parsed.path.startswith("/") else ""
if (
    not valid_component(username)
    or not valid_component(hostname)
    or not valid_component(database)
    or parsed.path != f"/{database}"
    or not isinstance(port, int)
    or not 1 <= port <= 65535
):
    fail()

print(hostname)
print(port)
print(username)
print(database)

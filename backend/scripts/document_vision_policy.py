"""Operator-only, fail-closed policy transition for the test/controlled database."""

import argparse
import asyncio
import os
import sys
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.documents.job_models import DocumentVisionPolicy
from app.documents.processing_policy import set_vision_policy
from app.documents.vision_config import get_vision_config


def _target_url(configured_settings: Settings) -> str:
    url = os.environ.get("DOCUMENT_VISION_POLICY_DATABASE_URL")
    if not url or not _matches_configured_database(url, configured_settings.DATABASE_URL):
        raise ValueError("controlled_test_database_required")
    return url


def _matches_configured_database(target: str, configured: str) -> bool:
    """Allow only the explicit operator target for this configured environment."""
    try:
        target_parts = urlsplit(target)
        configured_parts = urlsplit(configured)
        target_port = target_parts.port or 5432
        configured_port = configured_parts.port or 5432
    except ValueError:
        return False
    if (
        target_parts.query
        or target_parts.fragment
        or configured_parts.query
        or configured_parts.fragment
        or not target_parts.hostname
        or not configured_parts.hostname
    ):
        return False
    return (
        target_parts.scheme.lower() == configured_parts.scheme.lower()
        and target_parts.hostname.lower() == configured_parts.hostname.lower()
        and target_port == configured_port
        and target_parts.path.lstrip("/") == configured_parts.path.lstrip("/")
        and bool(target_parts.path.lstrip("/"))
    )


async def run(enable: bool, expected_epoch: int, apply: bool) -> int:
    configured_settings = Settings()
    engine = create_async_engine(_target_url(configured_settings))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            if not apply:
                policy = await db.get(DocumentVisionPolicy, 1)
                actual = policy.epoch if policy else 1
                if actual != expected_epoch:
                    print("expected_epoch_mismatch")
                    return 2
                print(f"dry_run enabled={enable} epoch={actual}")
                return 0
            config = get_vision_config(configured_settings) if enable else None
            try:
                await set_vision_policy(
                    db,
                    enabled=enable,
                    performed_by="operator-cli",
                    config=config,
                    expected_epoch=expected_epoch,
                )
            except ValueError as error:
                await db.rollback()
                print(str(error))
                return 2
            await db.commit()
            print("applied")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--enable", action="store_true")
    action.add_argument("--disable", action="store_true")
    parser.add_argument("--expected-epoch", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.enable, args.expected_epoch, args.apply))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

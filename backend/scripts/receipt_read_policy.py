"""Operator-only explicit receipt item export purpose; no model calls or header policy changes."""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.documents.receipt_read_config import get_receipt_read_config
from app.documents.receipt_read_policy import get_receipt_read_policy, set_receipt_read_policy
from app.finance.categorization_context import CategorizationError
from app.main import app as _app  # noqa: F401 - register complete metadata for standalone audit
from scripts.document_vision_policy import _matches_configured_database


def target_url(config: Settings) -> str:
    url = os.environ.get("RECEIPT_READ_POLICY_DATABASE_URL")
    if not url or not _matches_configured_database(url, config.DATABASE_URL):
        raise ValueError("explicit_matching_database_required")
    return url


async def run(enable: bool | None, expected_epoch: int | None, apply: bool) -> int:
    config = Settings()
    engine = create_async_engine(target_url(config))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            policy = await get_receipt_read_policy(db)
            if enable is None:
                print(f"enabled={policy.enabled} epoch={policy.epoch}")
                return 0
            if expected_epoch is None or expected_epoch != policy.epoch:
                print("expected_epoch_mismatch")
                return 2
            purpose = get_receipt_read_config(config)
            if enable and (not config.DOCUMENT_RECEIPT_ITEMS_ENABLED or purpose is None):
                print("receipt_read_configuration_inactive")
                return 2
            if not apply:
                print(f"dry_run enabled={enable} epoch={policy.epoch}")
                return 0
            try:
                policy = await set_receipt_read_policy(
                    db,
                    enabled=enable,
                    expected_epoch=expected_epoch,
                    config=purpose,
                    performed_by="operator-cli",
                )
            except CategorizationError as error:
                await db.rollback()
                print(error.code)
                return 2
            await db.commit()
            print(f"applied enabled={policy.enabled} epoch={policy.epoch}")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--enable", action="store_true")
    actions.add_argument("--disable", action="store_true")
    parser.add_argument("--expected-epoch", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.status and args.apply:
        parser.error("status is read-only")
    try:
        return asyncio.run(
            run(None if args.status else args.enable, args.expected_epoch, args.apply)
        )
    except ValueError:
        print("explicit_matching_database_required")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

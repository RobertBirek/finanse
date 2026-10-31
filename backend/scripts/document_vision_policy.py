"""Operator-only, fail-closed policy transition for the test/controlled database."""

import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.documents.job_models import DocumentVisionPolicy
from app.documents.processing_policy import set_vision_policy


def _target_url() -> str:
    url = os.environ.get("DOCUMENT_VISION_POLICY_DATABASE_URL")
    if not url or "127.0.0.1" not in url or "finanse_test" not in url:
        raise ValueError("controlled_test_database_required")
    return url


async def run(enable: bool, expected_epoch: int, apply: bool) -> int:
    engine = create_async_engine(_target_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            policy = await db.get(DocumentVisionPolicy, 1)
            actual = policy.epoch if policy else 1
            if actual != expected_epoch:
                print("expected_epoch_mismatch")
                return 2
            if not apply:
                print(f"dry_run enabled={enable} epoch={actual}")
                return 0
            await set_vision_policy(db, enabled=enable, performed_by="operator-cli")
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

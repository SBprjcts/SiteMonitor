"""Makes a registered user an admin (or removes it). There is no UI for this on purpose.

Usage:
    uv run python -m app.make_admin you@example.com
    uv run python -m app.make_admin you@example.com --revoke
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import SessionLocal, engine


async def set_admin(session: AsyncSession, email: str, is_admin: bool) -> bool:
    """Returns False if no user has that email."""
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return False
    user.is_admin = is_admin
    await session.commit()
    return True


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.make_admin")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="remove admin instead")
    args = parser.parse_args(argv)

    try:
        async with SessionLocal() as session:
            found = await set_admin(session, args.email, not args.revoke)
    finally:
        await engine.dispose()

    if not found:
        print(f"error: no user with the email {args.email}. Register first.", file=sys.stderr)
        return 1
    print(f"{args.email} is {'no longer' if args.revoke else 'now'} an admin.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

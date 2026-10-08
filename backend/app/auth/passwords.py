"""Password hashing with argon2. The real password is never stored or logged."""

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified when the email doesn't exist, so "no such user" takes as long as "wrong
# password" and login timing doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


async def hash_password(password: str) -> str:
    # Hashing is deliberately slow (tens of ms), so it runs off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    """True if the password matches. Pass None for the hash when the user doesn't exist."""
    matches = await asyncio.to_thread(_verify, password, password_hash or _DUMMY_HASH)
    return matches and password_hash is not None


def _verify(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False

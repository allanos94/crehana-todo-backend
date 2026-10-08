"""`Argon2PasswordHasher`: the `PasswordHasher` adapter backed by `pwdlib`
(design ADR-11). Argon2 is deliberately CPU-heavy, so every call is offloaded
to a worker thread with `asyncio.to_thread` instead of blocking the event
loop.
"""

import asyncio

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

_password_hash = PasswordHash((Argon2Hasher(),))

#: A fixed hash with no matching plaintext. `LoginUser` verifies against this
#: when the submitted email is unknown, so a login attempt against a
#: nonexistent account still pays the real Argon2 verification cost and
#: cannot be distinguished, by timing, from a wrong-password attempt.
DUMMY_HASH = _password_hash.hash("not-a-real-password-used-only-for-timing")


class Argon2PasswordHasher:
    """`PasswordHasher` adapter backed by `pwdlib`'s Argon2 implementation."""

    async def hash(self, raw: str) -> str:
        return await asyncio.to_thread(_password_hash.hash, raw)

    async def verify(self, raw: str, hashed: str) -> bool:
        return await asyncio.to_thread(_password_hash.verify, raw, hashed)

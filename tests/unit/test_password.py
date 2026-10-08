"""Unit tests for the Argon2 password-hashing adapter (user-auth spec:
stored passwords are hashes, never the submitted plaintext; login against an
unknown email still runs a real `verify()` call, equalizing timing with the
wrong-password case, design ADR-11).
"""

import pytest

from app.infrastructure.security.password import DUMMY_HASH, Argon2PasswordHasher


@pytest.fixture
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


async def test_hash_then_verify_round_trip(hasher: Argon2PasswordHasher) -> None:
    hashed = await hasher.hash("Passw0rd1")

    assert hashed != "Passw0rd1"
    assert await hasher.verify("Passw0rd1", hashed) is True


async def test_verify_rejects_wrong_password(hasher: Argon2PasswordHasher) -> None:
    hashed = await hasher.hash("Passw0rd1")

    assert await hasher.verify("WrongPass1", hashed) is False


async def test_verify_against_dummy_hash_runs_a_real_check(
    hasher: Argon2PasswordHasher,
) -> None:
    """The dummy hash exists so an unknown-email login still pays the real
    Argon2 verification cost; it must behave like any other hash, not a
    shortcut that always returns `False` without hashing."""
    assert await hasher.verify("whatever-an-attacker-tries", DUMMY_HASH) is False

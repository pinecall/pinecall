"""A password: the box's floor, the hash it is kept as, and the comparison that costs the same for nobody."""

import asyncio
from functools import cache

from runtime.exceptions import ValidationError
from runtime.kit import crypto


class PasswordTooShort(ValidationError):
    """Under the box's floor."""

    def __init__(self, shortest: int) -> None:
        super().__init__(f"a password is at least {shortest} characters")


# Verified when the address is nobody's, so the time taken does not say who is a member. Hashed
# on first use, not at import: argon2 costs tens of milliseconds.
@cache
def _nobodys_hash() -> str:
    return crypto.hash_password(crypto.random_token(32))


def check_password(password: str, shortest: int) -> None:
    """Refuse a password under the box's floor, before anything is hashed or spent on it."""
    if len(password) < shortest:
        raise PasswordTooShort(shortest)


# argon2id costs tens of milliseconds and 64 MiB: off the event loop.
async def hash_password(password: str, shortest: int) -> str:
    """The password hashed; refused before hashing when under the floor."""
    check_password(password, shortest)
    return await asyncio.to_thread(crypto.hash_password, password)


async def matches(password: str, kept: str | None) -> bool:
    """Whether the password is the one kept; nobody's costs a verification all the same."""
    return await asyncio.to_thread(crypto.verify_password, kept or _nobodys_hash(), password) and kept is not None

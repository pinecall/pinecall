"""Signed tokens: made and read with one key, each with its expiry."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import jwt as pyjwt

from pinecall_runtime.exceptions import Unauthorized
from pinecall_runtime.kit.time import now

ALGORITHM = "HS256"
JWT_PARTS = 3


def sign(claims: Mapping[str, Any], key: str, *, ttl: timedelta) -> str:
    """A token carrying the claims, expiring after the ttl."""
    moment = now()
    payload = {**claims, "iat": moment, "exp": moment + ttl}
    return pyjwt.encode(payload, key, algorithm=ALGORITHM)


def read_claims(token: str, key: str, *, what: str) -> dict[str, Any]:
    """The claims a token carries; Unauthorized when it is not ours, altered or expired."""
    try:
        return pyjwt.decode(token, key, algorithms=[ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise Unauthorized(f"this {what} expired") from None
    except pyjwt.InvalidTokenError:
        raise Unauthorized(f"this is not a {what} of this gateway") from None


def is_a_jwt(secret: str) -> bool:
    """Whether the secret is shaped as a token rather than an API key (which holds no dots)."""
    return secret.count(".") == JWT_PARTS - 1

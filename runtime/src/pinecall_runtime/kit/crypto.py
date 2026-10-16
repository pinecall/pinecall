"""Secrets at rest: the vault that seals them, the fingerprint a key is kept as, a password's hash."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from pinecall_runtime.exceptions import ConfigurationError, ServiceUnavailable

UNSET = (
    "PINECALL_VAULT_KEY is unset: every vendor key, mailbox and sign-in secret is sealed under "
    "it, so the gateway does not start without it. `Fernet.generate_key()` makes one"
)
NOT_A_KEY = (
    "PINECALL_VAULT_KEY holds something that is not a Fernet key: a comma-separated list of "
    "32-byte url-safe base64 keys, the newest first"
)


class Vault:
    """Fernet over the configured keys: the first seals, any listed opens."""

    def __init__(self, keys: str | None) -> None:
        if keys is None:
            raise ConfigurationError(UNSET)
        listed = [item.strip() for item in keys.split(",") if item.strip()]
        if not listed:
            raise ConfigurationError(NOT_A_KEY)
        try:
            self._fernet = MultiFernet([Fernet(key) for key in listed])
            self._newest = Fernet(listed[0])
        except ValueError:
            raise ConfigurationError(NOT_A_KEY) from None

    def seal(self, plain: str) -> str:
        """The text sealed under the newest key."""
        return self._fernet.encrypt(plain.encode()).decode()

    def open(self, sealed: str) -> str:
        """The text a seal holds; ServiceUnavailable when no listed key opens it."""
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            raise ServiceUnavailable("a sealed value is under a key the vault no longer lists") from None

    def reseal(self, sealed: str) -> str:
        """The same value, under the newest key; ServiceUnavailable when no listed key opens it."""
        try:
            return self._fernet.rotate(sealed.encode()).decode()
        except InvalidToken:
            raise ServiceUnavailable("a sealed value is under a key the vault no longer lists") from None

    def is_under_newest(self, sealed: str) -> bool:
        """Whether the newest key is the one the value is sealed under."""
        try:
            self._newest.decrypt(sealed.encode())
        except InvalidToken:
            return False
        return True


def fingerprint(secret: str) -> str:
    """The sha256 a key or token is kept and looked up as; the secret itself is never stored."""
    return hashlib.sha256(secret.encode()).hexdigest()


def random_token(nbytes: int = 32) -> str:
    """A url-safe secret of this many bytes."""
    return secrets.token_urlsafe(nbytes)


def random_id(prefix: str, nbytes: int = 8) -> str:
    """A hex id under a prefix: `k_…`, `org_…`, `call_…`."""
    return f"{prefix}{secrets.token_hex(nbytes)}"


_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    """argon2id."""
    return _HASHER.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    """Whether the password is the one hashed."""
    try:
        return _HASHER.verify(hashed, password)
    except VerifyMismatchError:
        return False

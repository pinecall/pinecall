"""The one error hierarchy: every error the runtime raises on purpose, with its HTTP status."""


class PinecallError(Exception):
    """Base of every deliberate error; the message is the sentence a person reads."""

    status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(PinecallError):
    """A value broke a contract; the message states the rule."""

    status = 400


class Unauthorized(PinecallError):
    """No key, a wrong one, or wrong credentials."""

    status = 401


class Forbidden(PinecallError):
    """A key that opens something, but not this."""

    status = 403


class NotFound(PinecallError):
    """Nothing by that name in the actor's scope."""

    status = 404


class Conflict(PinecallError):
    """A valid request against stored state that contradicts it."""

    status = 409


class PayloadTooLarge(PinecallError):
    """A body over what the endpoint takes."""

    status = 413


class TooManyRequests(PinecallError):
    """The same name asked too often in the window; `retry_after_s` says when to come back."""

    status = 429

    def __init__(self, message: str, *, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class QuotaExceeded(TooManyRequests):
    """A limit of the org is reached: which one, what was used and the limit."""

    def __init__(self, message: str, *, quota: str, used: float, limit: int) -> None:
        super().__init__(message)
        self.quota = quota
        self.used = used
        self.limit = limit


class UpstreamError(PinecallError):
    """A vendor, a carrier or an identity provider did not answer as it should."""

    status = 502


class GatewayUnavailable(UpstreamError):
    """The worker's gateway did not answer, or refused; `answered` is its status, None if unreachable."""

    def __init__(self, message: str, *, answered: int | None = None) -> None:
        super().__init__(message)
        self.answered = answered


class ServiceUnavailable(PinecallError):
    """This box lacks what the request needs: a key, the vault, an embedder, a database."""

    status = 503


class ConfigurationError(PinecallError):
    """The process cannot start with the environment it was given."""

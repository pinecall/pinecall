"""What a flow's steps came to: a call, a text, a template, and an extraction refused."""

from dataclasses import dataclass

from pinecall.errors import PinecallError


class ExtractRefused(PinecallError):
    """A model read nothing into the schema: no key ran it, no messages were left, or no answer."""

    def __init__(self, refused: str, message: str) -> None:
        """What refused it, and why."""
        super().__init__(message)
        self.refused = refused


@dataclass(frozen=True)
class Called:
    """What a call a flow placed came to; `refused` names why nothing rang."""

    answered: bool
    reason: str | None = None
    call: str | None = None
    refused: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class Texted:
    """What a text a flow sent came to; `refused` names why nothing was sent."""

    sent: bool
    call: str | None = None
    from_: str | None = None
    refused: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class Templated:
    """What a WhatsApp template a flow sent came to.

    `simulated`: the sandbox, where it is answered and never sent. `refused` names why none was.
    """

    sent: bool
    simulated: bool = False
    message_id: str | None = None
    from_: str | None = None
    call: str | None = None
    refused: str | None = None
    message: str | None = None

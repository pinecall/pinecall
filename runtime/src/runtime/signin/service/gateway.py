"""The gateway as a sign-in page reads it before anybody holds a key: what it is, and how it signs people in."""

from dataclasses import dataclass
from importlib.metadata import version

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.mail import service as mail
from runtime.platform import service as platform
from runtime.signin.service import google

# The distribution keeps its name whatever the package is imported as.
VERSION = version("pinecall-runtime")


@dataclass(frozen=True, slots=True)
class Gateway:
    """What a sign-in page draws itself from: the ways in this box offers, and the brand it carries."""

    version: str
    signup: bool
    min_password: int
    mail: bool
    brand: platform.Brand
    google: bool
    # Turnstile's site key where the operator set one: the page draws the widget, and a sign-up, its
    # resend and a forgotten password carry its token. None, and no endpoint asks for one.
    turnstile: str | None


# The mailbox is asked for first: the outbox reads it on a session of its own, before this request's
# session holds a connection.
async def describe(
    session: AsyncSession, outbox: mail.Outbox, *, signup: bool, min_password: int, turnstile: str | None
) -> Gateway:
    """What this gateway is and how it signs people in."""
    mails = await outbox.mailbox_for(None) is not None
    brand = await platform.get_brand(session)
    offers_google = await google.client_id_of(session) is not None
    return Gateway(VERSION, signup, min_password, mails, brand, offers_google, turnstile)

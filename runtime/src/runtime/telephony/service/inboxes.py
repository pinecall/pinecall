"""The mailboxes a gateway reads: the ones an address of answers email, each leased to one gateway at a time."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Channel, Env
from runtime.kit.crypto import Vault
from runtime.kit.time import now
from runtime.scoping import box_wide
from runtime.telephony.repository import CarrierRepository, EmailInboxRepository, RouteRepository
from runtime.telephony.service.accounts import carrier_of
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_box import Cursor


@dataclass(frozen=True, slots=True)
class MailReader:
    """The app whose flows read an address's emails, in the env the address answers in."""

    org: str
    env: Env
    app: str


@dataclass(frozen=True, slots=True)
class Leased:
    """A mailbox this gateway reads now, and where the reading stood."""

    account: EmailAccount
    cursor: Cursor


async def list_routed_mailboxes(session: AsyncSession, vault: Vault) -> list[EmailAccount]:
    """Every org's mailbox an address of answers on the channel email, opened."""
    with box_wide():
        rows = await CarrierRepository(session).list_routed_mailboxes()
    opened = (carrier_of(vault, row) for row in rows)
    return [account for account in opened if isinstance(account, EmailAccount)]


async def lease_inbox(session: AsyncSession, account: EmailAccount, *, by: str, for_s: float) -> Leased | None:
    """The mailbox leased to this gateway for a while, and where its reading stood; None while another reads it."""
    at = now()
    with box_wide():
        row = await EmailInboxRepository(session).lease(
            account.org, account.id, by=by, until=at + timedelta(seconds=for_s), at=at
        )
    return None if row is None else Leased(account, Cursor(row.uid_validity, row.last_uid))


async def move_inbox(session: AsyncSession, account: EmailAccount, cursor: Cursor, error: str | None) -> None:
    """Say where the reading of the mailbox stands after a pass, and what went wrong in it."""
    with box_wide():
        await EmailInboxRepository(session).move(
            account.org,
            account.id,
            uid_validity=cursor.uid_validity,
            last_uid=cursor.last_uid,
            at=now(),
            error=error,
        )


# A number is held once a channel across the box, so the address names one route at most.
async def find_mail_reader(session: AsyncSession, account: EmailAccount) -> MailReader | None:
    """The app whose flows read the mailbox's emails, when its address names one; None: its agent answers them."""
    with box_wide():
        route = await RouteRepository(session).find_at(Channel.email, account.id)
    if route is None or route.app is None or route.org != account.org:
        return None
    return MailReader(org=route.org, env=route.env, app=route.app)

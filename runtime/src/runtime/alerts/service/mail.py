"""An alert by mail: to the org's admins and the box's operators, once an hour per subject; the quiet orgs' digest."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.accounts import service as accounts
from runtime.actor import Scope
from runtime.alerts.repository import AlertRepository
from runtime.alerts.service import kinds
from runtime.kit.time import now
from runtime.mail import service as mail
from runtime.platform import service as platform
from runtime.wire.base import WireModel
from runtime.wire.feed import OrgQuiet

# A refusal can come once a call: a person is mailed once an hour for each subject of each kind.
MAILED_EVERY = timedelta(hours=1)
# Whose the digest of the quiet newborns is, in its footer.
THE_NEWBORNS = "the newborn orgs"


def alert_email(to: str, brand: platform.Brand, *, title: str, said: str, whose: str, link: str | None) -> mail.Email:
    """An alert of an org, mailed to a person who keeps an eye on it: what happened, and where to look."""
    footer = f"Sent by {brand.name} for {whose} · every alert is listed under Settings ▸ Alerts"
    look = "" if link is None else mail.button("Open the console", link, brand.accent) + mail.fallback(link)
    body = mail.heading(title) + mail.paragraph(said) + look
    text = "\n\n".join([title, said, *([] if link is None else [f"Open the console:\n\n{link}"]), footer])
    return mail.Email(to, f"{title} · {whose}", text, mail.frame(said, body, footer, brand))


# The emails leave once the alert's row is committed and never when its transaction rolls back
# (`post_after_commit`): the row says `mailed`, and the next alert of the hour reads that row.
async def mail_alert(
    session: AsyncSession,
    outbox: mail.Outbox,
    address: str | None,
    scope: Scope,
    kind: kinds.Kind[Any],
    alert: WireModel,
) -> bool:
    """Mail the alert to the org's admins and the box's operators, once an hour per subject; whether it goes."""
    if kind.words is None:
        return False
    subject = kind.subject(alert)
    if await AlertRepository(session).has_mailed_since(scope.org, scope.env, kind.name, subject, now() - MAILED_EVERY):
        return False
    admins = [] if kind.operators_alone else await accounts.list_admin_addresses(session, scope.org)
    operators = [each for each in await accounts.list_operator_addresses(session) if each not in admins]
    if not admins and not operators:
        return False
    brand = await platform.get_brand(session)
    org = await accounts.find_org(session, scope.org)
    whose = f"{scope.org if org is None else org.name} ({scope.env.value})"
    title, said = kind.words(alert)
    link = kinds.link_of(address, scope.env, kind, alert)
    goes = False
    for to, through in [(each, scope.org) for each in admins] + [(each, None) for each in operators]:
        email = alert_email(to, brand, title=title, said=said, whose=whose, link=link)
        goes = await outbox.post_after_commit(session, through, email) or goes
    return goes


async def mail_quiet_digest(
    session: AsyncSession, outbox: mail.Outbox, address: str | None, quiets: Sequence[OrgQuiet]
) -> bool:
    """Mail the box's operators the newborn orgs a sweep found quiet, as one list; whether it goes."""
    operators = await accounts.list_operator_addresses(session)
    if not quiets or not operators:
        return False
    brand = await platform.get_brand(session)
    title, said = kinds.word_quiet_digest(quiets)
    link = None if address is None else f"{address}{kinds.OPERATORS_SCREEN}"
    goes = False
    for to in operators:
        email = alert_email(to, brand, title=title, said=said, whose=THE_NEWBORNS, link=link)
        goes = await outbox.post_after_commit(session, None, email) or goes
    return goes

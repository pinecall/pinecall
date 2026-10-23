"""Who an alert is mailed to and what it says: the org's admins and the box's operators, once an hour per subject."""

from collections.abc import Callable
from datetime import timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.service import emails, members, orgs
from pinecall_runtime.alerts.repository import AlertRepository
from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import NotFound
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.text import JsonObject
from pinecall_runtime.kit.time import now
from pinecall_runtime.platform import service as platform

# A refusal can come once a call: a person is mailed once an hour for each subject of each kind.
MAILED_EVERY = timedelta(hours=1)
# The console screen that lists the alerts, under the world's own prefix.
ALERTS_SCREEN = {Env.production: "/settings/alerts", Env.sandbox: "/sandbox/settings/alerts"}


class Mailer(Protocol):
    """What sends an email in the background: the org's mailbox, else the box's."""

    async def post(self, org: str | None, email: emails.Email) -> bool:
        """Send in the background; False when nothing can send it."""
        ...


def subject_of(kind: str, data: JsonObject) -> str:
    """What an alert is about within its kind: the monitor, the app, the quota; the org's spend has one."""
    match kind:
        case "monitor.fired":
            return str(data.get("monitor") or "")
        case "app.failed":
            return str(data.get("app") or "")
        case "credits.exhausted":
            return str(data.get("quota") or "")
        case _:
            return ""


def _monitor(data: JsonObject) -> tuple[str, str]:
    side = "above" if data.get("above") else "below"
    agent = f" for {data['agent']}" if data.get("agent") else ""
    said = (
        f"{data.get('metric')} was {data.get('value')} over the last {data.get('window_days')} days{agent}, "
        f"{side} its line of {data.get('threshold')}."
    )
    return f"Monitor {data.get('name')} fired", said


def _spend(data: JsonObject) -> tuple[str, str]:
    said = (
        f"Today's calls cost ${data.get('today_usd')}, {data.get('multiple')} times a usual day "
        f"(${data.get('usual_usd')})."
    )
    return "Unusual spend today", said


def _quota(data: JsonObject) -> tuple[str, str]:
    quota, used, limit = data.get("quota"), data.get("used"), data.get("limit")
    said = f"A request was refused because the {quota} quota ran out: {used} of {limit}."
    return f"Out of {data.get('quota')}", said


def _app(data: JsonObject) -> tuple[str, str]:
    why = str(data.get("why") or "").split("\n")[0]
    release = f" release {data['release']}" if data.get("release") is not None else ""
    said = f"The hosted app {data.get('app')}{release} did not build, start or stay up: {why}"
    return f"{data.get('app')} went down", said


WORDED: dict[str, Callable[[JsonObject], tuple[str, str]]] = {
    "monitor.fired": _monitor,
    "spend.unusual": _spend,
    "credits.exhausted": _quota,
    "app.failed": _app,
}


async def mail_alert(
    session: AsyncSession, outbox: Mailer, address: str | None, scope: Scope, kind: str, data: JsonObject
) -> bool:
    """Mail the alert to the org's admins and the box's operators, once an hour per subject; whether it went."""
    if await AlertRepository(session).mailed_since(
        scope.org, scope.env, kind, subject_of(kind, data), now() - MAILED_EVERY
    ):
        return False
    admins = await members.admins_of(session, scope.org)
    operators = [email for email in await members.operators_of_the_box(session) if email not in admins]
    if not admins and not operators:
        return False
    brand = await platform.get_brand(session)
    try:
        whose = f"{(await orgs.get_org(session, scope.org)).name} ({scope.env.value})"
    except NotFound:
        whose = f"{scope.org} ({scope.env.value})"
    title, said = WORDED[kind](data)
    link = None if address is None else f"{address}{ALERTS_SCREEN[scope.env]}"
    went = False
    for email, org in [(each, scope.org) for each in admins] + [(each, None) for each in operators]:
        mailed = emails.alert_email(email, brand, title=title, said=said, whose=whose, link=link)
        went = await outbox.post(org, mailed) or went
    return went

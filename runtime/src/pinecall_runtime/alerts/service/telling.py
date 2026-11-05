"""Who an alert is mailed to and what it says: the org's admins and the box's operators, once an hour per subject."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
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
# Said once for its subject, ever: a newborn org is pointed at once, not every hour it stays quiet.
SAID_ONCE = frozenset({"org.quiet"})
# The operators' alone: an org is never mailed that nobody has called it.
OPERATORS_ALONE = frozenset({"org.quiet"})
# The console screen that lists the alerts, under the env's own prefix; a vendor's failure opens the call.
ALERTS_SCREEN = {Env.production: "/settings/alerts", Env.sandbox: "/sandbox/settings/alerts"}
CALL_SCREEN = {Env.production: "/calls/{call}", Env.sandbox: "/sandbox/calls/{call}"}
# What a vendor's stage is called to a person.
STAGE_NAMED = {"llm": "model", "stt": "transcription", "tts": "voice"}
# Where the operator finds the org the alert names: the console's Box, its organizations.
OPERATORS_SCREEN = "/box/orgs"


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
        case "vendor.failed":
            return str(data.get("vendor") or data.get("stage") or "")
        case "org.quiet":
            return str(data.get("org") or "")
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
    calls = [str(call) for call in data.get("calls") or () if isinstance(call, str)]
    if quota == "concurrent_calls" and calls:
        named = ", ".join(calls)
        each = "it" if len(calls) == 1 else "them"
        said = (
            f"A call was refused because all {limit} of your calls at once were in use: {named} still open. "
            f"End {each} in the console's Calls, or wait for {each} to end; a test and a simulation each "
            f"count as a call."
        )
        return "All your calls at once in use", said
    said = f"A request was refused because the {quota} quota ran out: {used} of {limit}."
    return f"Out of {data.get('quota')}", said


def _vendor(data: JsonObject) -> tuple[str, str]:
    stage = STAGE_NAMED.get(str(data.get("stage")), str(data.get("stage")))
    vendor = str(data.get("vendor") or "")
    whose = vendor or f"the {stage}"
    model = f" ({data['model']})" if data.get("model") else ""
    errors = int(data.get("errors") or 1)
    times = "" if errors == 1 else f", {errors} times"
    what = str(data.get("message") or "").split("\n")[0]
    if data.get("own_key"):
        advice = (
            f"The call ran {whose} on your own key: check the key and its quota in Settings ▸ Providers, "
            f"or remove it to run on Pinecall's."
        )
    else:
        advice = "The call ran it on Pinecall's key; the operators were told too."
    said = f"On call {data.get('call')}, {whose}{model} failed as the {stage}{times}: {what} {advice}"
    return f"{vendor or f'The {stage}'} failed a call", said


def _quiet_had(data: JsonObject) -> str:
    calls, failed = int(data.get("calls") or 0), int(data.get("failed") or 0)
    if calls == 0:
        return "has made no call yet"
    plural = "" if calls == 1 else "s"
    return f"has had no call that went well: {calls} call{plural}, {failed} failed on a vendor"


def _quiet(data: JsonObject) -> tuple[str, str]:
    said = f"{data.get('name')} ({data.get('org')}) signed up a day ago and {_quiet_had(data)}. Reach out."
    return f"{data.get('name')} is quiet", said


# One mail a sweep, however many signed up the day before: a launch day is hundreds of orgs, and
# an operator mailed hundreds of times reads none of them.
async def mail_quiet_digest(
    session: AsyncSession, outbox: Mailer, address: str | None, quiets: Sequence[JsonObject]
) -> bool:
    """Mail the box's operators the newborn orgs a sweep found quiet, as one list; whether it went."""
    operators = await members.operators_of_the_box(session)
    if not quiets or not operators:
        return False
    brand = await platform.get_brand(session)
    count = len(quiets)
    title = f"{count} new org{'' if count == 1 else 's'} signed up a day ago and {'is' if count == 1 else 'are'} quiet"
    said = " · ".join(f"{data.get('name')} ({data.get('org')}) {_quiet_had(data)}" for data in quiets) + ". Reach out."
    link = None if address is None else f"{address}{OPERATORS_SCREEN}"
    went = False
    for email in operators:
        mailed = emails.alert_email(email, brand, title=title, said=said, whose="the newborn orgs", link=link)
        went = await outbox.post(None, mailed) or went
    return went


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
    "vendor.failed": _vendor,
    "org.quiet": _quiet,
}


def link_of(address: str | None, scope: Scope, kind: str, data: JsonObject) -> str | None:
    """Where the mail's button opens: the call a vendor failed, the Box for the operators', else the alerts."""
    if address is None:
        return None
    if kind == "vendor.failed" and data.get("call"):
        return f"{address}{CALL_SCREEN[scope.env].format(call=data['call'])}"
    if kind in OPERATORS_ALONE:
        return f"{address}{OPERATORS_SCREEN}"
    return f"{address}{ALERTS_SCREEN[scope.env]}"


async def mail_alert(
    session: AsyncSession, outbox: Mailer, address: str | None, scope: Scope, kind: str, data: JsonObject
) -> bool:
    """Mail the alert to the org's admins and the box's operators, once an hour per subject; whether it went."""
    since = datetime.min.replace(tzinfo=UTC) if kind in SAID_ONCE else now() - MAILED_EVERY
    if await AlertRepository(session).mailed_since(scope.org, scope.env, kind, subject_of(kind, data), since):
        return False
    admins = [] if kind in OPERATORS_ALONE else await members.admins_of(session, scope.org)
    operators = [email for email in await members.operators_of_the_box(session) if email not in admins]
    if not admins and not operators:
        return False
    brand = await platform.get_brand(session)
    try:
        whose = f"{(await orgs.get_org(session, scope.org)).name} ({scope.env.value})"
    except NotFound:
        whose = f"{scope.org} ({scope.env.value})"
    title, said = WORDED[kind](data)
    link = link_of(address, scope, kind, data)
    went = False
    for email, org in [(each, scope.org) for each in admins] + [(each, None) for each in operators]:
        mailed = emails.alert_email(email, brand, title=title, said=said, whose=whose, link=link)
        went = await outbox.post(org, mailed) or went
    return went

"""The kinds of alert: each one's name, what it is about, what its mail says, who hears it, and how often it is said."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from runtime.alerts.models import AlertKind
from runtime.enums import Env, Stage
from runtime.wire.base import WireModel
from runtime.wire.events import CreditsExhausted, MonitorFired, SpendUnusual, VendorFailed
from runtime.wire.feed import AppFailed, OrgQuiet

# A mail's title, and what it says.
type Words = tuple[str, str]
# From now, the moment since which a kind said once counts as said.
type Since = Callable[[datetime], datetime]

# The console screen that lists the alerts, under the env's own prefix; a vendor's failure opens the call.
ALERTS_SCREEN = {Env.production: "/settings/alerts", Env.sandbox: "/sandbox/settings/alerts"}
CALL_SCREEN = {Env.production: "/calls/{call}", Env.sandbox: "/sandbox/calls/{call}"}
# Where the operator finds the org the alert names: the console's Box, its organizations.
OPERATORS_SCREEN = "/box/orgs"
# What a vendor's stage is called to a person.
STAGE_NAMED = {Stage.llm: "model", Stage.stt: "transcription", Stage.tts: "voice"}
# The quota whose refusal names the calls that hold it.
CONCURRENT_CALLS = "concurrent_calls"


def since_midnight(at: datetime) -> datetime:
    """The UTC midnight before the moment: said once a day."""
    return at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def since_ever(_at: datetime) -> datetime:
    """Before every alert: said once for its subject, ever."""
    return datetime.min.replace(tzinfo=UTC)


def alerts_screen(_alert: WireModel, env: Env) -> str:
    """The console screen that lists the env's alerts."""
    return ALERTS_SCREEN[env]


def call_screen(failed: VendorFailed, env: Env) -> str:
    """The console screen of the call a vendor failed."""
    return CALL_SCREEN[env].format(call=failed.call) if failed.call else ALERTS_SCREEN[env]


def operators_screen(_alert: WireModel, _env: Env) -> str:
    """The console screen where the operator finds the org an alert of theirs names."""
    return OPERATORS_SCREEN


# Until 2026-11 a kind had no home: its name was a row of one table, its subject a branch of a `match`,
# its words a row of another table, its audience two sets, and its "already said" a mechanism of its
# own, in five files of three domains. A kind is one record here, and a new one is one more.
@dataclass(frozen=True, slots=True)
class Kind[A: WireModel]:
    """One kind of alert: the type its log entry and its post carry, and everything that differs by kind."""

    name: AlertKind
    # What the alert is about within its kind: the monitor, the app, the quota.
    subject: Callable[[A], str]
    # What its mail says. None is never mailed one by one: its sweep mails the operators one digest.
    words: Callable[[A], Words] | None
    # Since when one already raised for the subject means this one is not: None raises it every time.
    once_since: Since | None = None
    # The operators' alone: nobody of the org is mailed it, and the org's webhook never hears it.
    operators_alone: bool = False
    # Where the mail's button opens.
    screen: Callable[[A, Env], str] = alerts_screen


def _monitor(fired: MonitorFired) -> Words:
    side = "above" if fired.above else "below"
    agent = f" for {fired.agent}" if fired.agent else ""
    said = (
        f"{fired.metric} was {fired.value} over the last {fired.window_days} days{agent}, "
        f"{side} its line of {fired.threshold}."
    )
    return f"Monitor {fired.name} fired", said


def _spend(unusual: SpendUnusual) -> Words:
    said = f"Today's calls cost ${unusual.today_usd}, {unusual.multiple} times a usual day (${unusual.usual_usd})."
    return "Unusual spend today", said


def _quota(exhausted: CreditsExhausted) -> Words:
    quota, used, limit, calls = exhausted.quota, exhausted.used, exhausted.limit, exhausted.calls
    if quota == CONCURRENT_CALLS and calls:
        named = ", ".join(calls)
        each = "it" if len(calls) == 1 else "them"
        said = (
            f"A call was refused because all {limit} of your calls at once were in use: {named} still open. "
            f"End {each} in the console's Calls, or wait for {each} to end; a test and a simulation each "
            f"count as a call."
        )
        return "All your calls at once in use", said
    said = f"A request was refused because the {quota} quota ran out: {used} of {limit}."
    return f"Out of {quota}", said


def _vendor(failed: VendorFailed) -> Words:
    stage = STAGE_NAMED[Stage(failed.stage)]
    vendor = failed.vendor
    whose = vendor or f"the {stage}"
    model = f" ({failed.model})" if failed.model else ""
    errors = failed.errors or 1
    times = "" if errors == 1 else f", {errors} times"
    what = failed.message.split("\n")[0]
    if failed.own_key:
        advice = (
            f"The call ran {whose} on your own key: check the key and its quota in Settings ▸ Providers, "
            f"or remove it to run on Pinecall's."
        )
    else:
        advice = "The call ran it on Pinecall's key; the operators were told too."
    said = f"On call {failed.call}, {whose}{model} failed as the {stage}{times}: {what} {advice}"
    return f"{vendor or f'The {stage}'} failed a call", said


def _app(failed: AppFailed) -> Words:
    why = failed.why.split("\n")[0]
    release = f" release {failed.release}" if failed.release is not None else ""
    said = f"The hosted app {failed.app}{release} did not build, start or stay up: {why}"
    return f"{failed.app} went down", said


def _quiet_had(quiet: OrgQuiet) -> str:
    if quiet.calls == 0:
        return "has made no call yet"
    plural = "" if quiet.calls == 1 else "s"
    return f"has had no call that went well: {quiet.calls} call{plural}, {quiet.failed} failed on a vendor"


# One mail a sweep, however many signed up the day before: a launch day is hundreds of orgs, and
# an operator mailed hundreds of times reads none of them.
def word_quiet_digest(quiets: Sequence[OrgQuiet]) -> Words:
    """What the operators' one mail says of the newborn orgs a sweep found quiet."""
    count = len(quiets)
    title = f"{count} new org{'' if count == 1 else 's'} signed up a day ago and {'is' if count == 1 else 'are'} quiet"
    said = " · ".join(f"{quiet.name} ({quiet.org}) {_quiet_had(quiet)}" for quiet in quiets) + ". Reach out."
    return title, said


MONITOR_FIRED = Kind[MonitorFired](AlertKind.monitor_fired, lambda fired: fired.monitor, _monitor)
# The org's spend has one subject: the org's spend.
SPEND_UNUSUAL = Kind[SpendUnusual](AlertKind.spend_unusual, lambda _unusual: "", _spend, once_since=since_midnight)
CREDITS_EXHAUSTED = Kind[CreditsExhausted](AlertKind.credits_exhausted, lambda exhausted: str(exhausted.quota), _quota)
# An app's names no agent.
APP_FAILED = Kind[AppFailed](AlertKind.app_failed, lambda failed: failed.app, _app)
VENDOR_FAILED = Kind[VendorFailed](
    AlertKind.vendor_failed, lambda failed: failed.vendor or failed.stage, _vendor, screen=call_screen
)
# A newborn org is pointed at once, not every hour it stays quiet, and an org is never mailed that
# nobody has called it.
ORG_QUIET = Kind[OrgQuiet](
    AlertKind.org_quiet,
    lambda quiet: quiet.org,
    None,
    once_since=since_ever,
    operators_alone=True,
    screen=operators_screen,
)

# The alerts, each by the wire model that is raised. A monitor is said once a day by its own row
# (`MonitorRepository.mark_fired`), which the release before 2026-11 races to as well.
KINDS: dict[type[WireModel], Kind[Any]] = {
    MonitorFired: MONITOR_FIRED,
    SpendUnusual: SPEND_UNUSUAL,
    CreditsExhausted: CREDITS_EXHAUSTED,
    AppFailed: APP_FAILED,
    VendorFailed: VENDOR_FAILED,
    OrgQuiet: ORG_QUIET,
}
NAMED: dict[AlertKind, Kind[Any]] = {kind.name: kind for kind in KINDS.values()}


def kind_of(alert: WireModel) -> Kind[Any]:
    """The kind of an alert, by the wire model it is."""
    return KINDS[type(alert)]


def link_of(address: str | None, env: Env, kind: Kind[Any], alert: WireModel) -> str | None:
    """Where the mail's button opens: the screen of the alert's kind, at the box's address; None where it has none."""
    return None if address is None else f"{address}{kind.screen(alert, env)}"

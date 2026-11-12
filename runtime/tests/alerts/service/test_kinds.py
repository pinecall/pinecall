"""What an alert's mail says and where its button opens: a quota naming the calls, a vendor, a quiet org."""

from runtime.alerts.service.kinds import (
    CREDITS_EXHAUSTED,
    MONITOR_FIRED,
    ORG_QUIET,
    VENDOR_FAILED,
    kind_of,
    link_of,
    since_ever,
    word_quiet_digest,
)
from runtime.enums import Env
from runtime.wire.events import CreditsExhausted, MonitorFired, VendorFailed
from runtime.wire.feed import OrgQuiet

ADDRESS = "https://cloud.example.test"


def test_a_concurrent_calls_refusal_names_the_calls_still_open_and_what_to_do() -> None:
    """The mail says which calls hold the seats and how to free one; another quota reads as before."""
    seats = CreditsExhausted.model_validate(
        {"org": "org_1", "quota": "concurrent_calls", "used": 1.0, "limit": 1, "calls": ["call_8ff9"]}
    )
    assert kind_of(seats) is CREDITS_EXHAUSTED and CREDITS_EXHAUSTED.words is not None
    title, said = CREDITS_EXHAUSTED.words(seats)
    assert title == "All your calls at once in use"
    assert "call_8ff9 still open" in said and "End it in the console's Calls" in said
    assert "a test and a simulation each count as a call" in said
    minutes = CreditsExhausted.model_validate(
        {"org": "org_1", "quota": "minutes", "used": 30.0, "limit": 30, "calls": []}
    )
    assert CREDITS_EXHAUSTED.words(minutes) == (
        "Out of minutes",
        "A request was refused because the minutes quota ran out: 30.0 of 30.",
    )
    assert CREDITS_EXHAUSTED.subject(minutes) == "minutes"


def test_a_vendors_failure_says_whose_key_it_ran_on_and_opens_the_call() -> None:
    """On the org's own key the mail points at Settings ▸ Providers; on a lent one it says the operators know."""
    own = VendorFailed(
        call="call_1d6b",
        stage="llm",
        vendor="google",
        model=None,
        code="component_failed",
        message="gemini llm: server error, status_code=504",
        own_key=True,
        errors=2,
    )
    assert kind_of(own) is VENDOR_FAILED and VENDOR_FAILED.words is not None
    title, said = VENDOR_FAILED.words(own)
    assert title == "google failed a call"
    assert said.startswith("On call call_1d6b, google failed as the model, 2 times: gemini llm")
    assert "on your own key" in said and "Settings ▸ Providers" in said
    assert VENDOR_FAILED.subject(own) == "google"
    assert link_of(ADDRESS, Env.sandbox, VENDOR_FAILED, own) == f"{ADDRESS}/sandbox/calls/call_1d6b"
    assert link_of(ADDRESS, Env.production, VENDOR_FAILED, own) == f"{ADDRESS}/calls/call_1d6b"
    lent = own.model_copy(
        update={"own_key": False, "errors": 1, "vendor": "", "message": "the model said nothing within 12s"}
    )
    title, said = VENDOR_FAILED.words(lent)
    assert title == "The model failed a call"
    assert "the model failed as the model: the model said nothing" in said
    assert "on Pinecall's key; the operators were told too" in said
    assert VENDOR_FAILED.subject(lent) == "llm"


def test_a_quiet_org_is_the_operators_alone_said_once_and_opens_the_box() -> None:
    """Named with its calls and how many failed; nobody of the org is mailed, it is said once, never one by one."""
    quiet = OrgQuiet(org="org_ce5e", name="ClickBoss", created_at=1793805000.0, calls=3, failed=2)
    assert word_quiet_digest([quiet]) == (
        "1 new org signed up a day ago and is quiet",
        "ClickBoss (org_ce5e) has had no call that went well: 3 calls, 2 failed on a vendor. Reach out.",
    )
    silent = quiet.model_copy(update={"org": "org_77aa", "name": "Nobody", "calls": 0, "failed": 0})
    title, said = word_quiet_digest([quiet, silent])
    assert title == "2 new orgs signed up a day ago and are quiet"
    assert said.endswith(" · Nobody (org_77aa) has made no call yet. Reach out.")
    assert kind_of(quiet) is ORG_QUIET
    assert ORG_QUIET.operators_alone and ORG_QUIET.once_since is since_ever and ORG_QUIET.words is None
    assert ORG_QUIET.subject(quiet) == "org_ce5e"
    assert link_of(ADDRESS, Env.sandbox, ORG_QUIET, quiet) == f"{ADDRESS}/box/orgs"


def test_a_monitors_mail_opens_the_alerts_of_its_env_and_nothing_where_the_box_has_no_address() -> None:
    fired = MonitorFired(
        monitor="mon_1",
        name="slow",
        metric="e2e_median_s",
        above=True,
        threshold=2.0,
        value=2.5,
        window_days=7,
        agent=None,
        env=Env.production,
        day="2026-11-12",
    )
    assert kind_of(fired) is MONITOR_FIRED and MONITOR_FIRED.subject(fired) == "mon_1"
    assert link_of(ADDRESS, Env.production, MONITOR_FIRED, fired) == f"{ADDRESS}/settings/alerts"
    assert link_of(ADDRESS, Env.sandbox, MONITOR_FIRED, fired) == f"{ADDRESS}/sandbox/settings/alerts"
    assert link_of(None, Env.production, MONITOR_FIRED, fired) is None

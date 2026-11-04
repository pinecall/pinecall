"""What an alert's mail says and where its button opens: a quota naming the calls, a vendor, a quiet org."""

from pinecall_runtime.alerts.service.telling import OPERATORS_ALONE, SAID_ONCE, WORDED, link_of, subject_of
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope

ADDRESS = "https://cloud.example.test"


def test_a_concurrent_calls_refusal_names_the_calls_still_open_and_what_to_do() -> None:
    """The mail says which calls hold the seats and how to free one; another quota reads as before."""
    data = {"org": "org_1", "quota": "concurrent_calls", "used": 1.0, "limit": 1, "calls": ["call_8ff9"]}
    title, said = WORDED["credits.exhausted"](data)
    assert title == "All your calls at once in use"
    assert "call_8ff9 still open" in said and "End it in the console's Calls" in said
    assert "a test and a simulation each count as a call" in said
    minutes: dict[str, object] = {"org": "org_1", "quota": "minutes", "used": 30.0, "limit": 30, "calls": []}
    assert WORDED["credits.exhausted"](minutes) == (
        "Out of minutes",
        "A request was refused because the minutes quota ran out: 30.0 of 30.",
    )


def test_a_vendors_failure_says_whose_key_it_ran_on_and_opens_the_call() -> None:
    """On the org's own key the mail points at Settings ▸ Providers; on a lent one it says the operators know."""
    own = {
        "call": "call_1d6b",
        "stage": "llm",
        "vendor": "google",
        "model": None,
        "code": "component_failed",
        "message": "gemini llm: server error, status_code=504",
        "own_key": True,
        "errors": 2,
    }
    title, said = WORDED["vendor.failed"](own)
    assert title == "google failed a call"
    assert said.startswith("On call call_1d6b, google failed as the model, 2 times: gemini llm")
    assert "on your own key" in said and "Settings ▸ Providers" in said
    assert subject_of("vendor.failed", own) == "google"
    assert link_of(ADDRESS, Scope("org_1", Env.sandbox), "vendor.failed", own) == f"{ADDRESS}/sandbox/calls/call_1d6b"
    lent = {**own, "own_key": False, "errors": 1, "vendor": "", "message": "the model said nothing within 12s"}
    title, said = WORDED["vendor.failed"](lent)
    assert title == "The model failed a call"
    assert "the model failed as the model: the model said nothing" in said
    assert "on Pinecall's key; the operators were told too" in said
    assert subject_of("vendor.failed", lent) == "llm"


def test_a_quiet_org_is_the_operators_alone_said_once_and_opens_the_box() -> None:
    """The alert names the org, its calls and how many failed; nobody of the org is mailed, and only once."""
    quiet = {"org": "org_ce5e", "name": "ClickBoss", "created_at": 1793805000.0, "calls": 3, "failed": 2}
    title, said = WORDED["org.quiet"](quiet)
    assert title == "ClickBoss is quiet"
    assert said == (
        "ClickBoss (org_ce5e) signed up a day ago and has had no call that went well: "
        "3 calls, 2 failed on a vendor. Reach out."
    )
    none = WORDED["org.quiet"]({**quiet, "calls": 0, "failed": 0})[1]
    assert "has made no call yet" in none
    assert "org.quiet" in OPERATORS_ALONE and "org.quiet" in SAID_ONCE
    assert subject_of("org.quiet", quiet) == "org_ce5e"
    assert link_of(ADDRESS, Scope("org_ce5e", Env.sandbox), "org.quiet", quiet) == f"{ADDRESS}/box/orgs"
    assert link_of(ADDRESS, Scope("org_ce5e", Env.production), "monitor.fired", {}) == f"{ADDRESS}/settings/alerts"
    assert link_of(None, Scope("org_ce5e", Env.production), "monitor.fired", {}) is None

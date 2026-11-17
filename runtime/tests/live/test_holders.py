"""Who holds what on a gateway: a person's own phone, one at a time, and a line that is never left with nobody."""

import pytest

from runtime import shared_state
from runtime.actor import THE_ORGS_OWN, Scope
from runtime.agents.declaration import Declaration
from runtime.enums import Env
from runtime.live.parts import LiveParts
from runtime.wire.commands import AgentRegister
from tests.conftest import needs_the_database, until

SCOPE = Scope("org_1", Env.production)


async def takes_rings(live: LiveParts, app: str, agent: str) -> None:
    """An app's socket on the gateway: it holds the agent and takes the rings nobody claimed."""
    await live.holders.register(app, SCOPE, agent, AgentRegister(routes=[]), Declaration(slug=agent))


async def watches(live: LiveParts, app: str, agent: str) -> None:
    """A terminal's socket beside the app's: it holds the agent and takes no ring."""
    wanted = AgentRegister(routes=[], takes_unclaimed=False)
    await live.holders.register(app, SCOPE, agent, wanted, Declaration(slug=agent))


def rings_at(live: LiveParts, agent: str) -> str | None:
    """The app a ring at the agent lands in, as this gateway sees it."""
    taking = live.holders.find_ring_taker(SCOPE, agent, None)
    return None if taking is None else taking.owner


# K F2 (2026-10-23): `line from` added a phone beside the one before, and `line forget` then took both.
@needs_the_database
async def test_a_persons_phone_said_again_replaces_the_one_before_and_forget_takes_the_one_left(
    live: LiveParts,
) -> None:
    holders = live.holders
    holders.route_phone(Env.sandbox, "+34607827824", "m_ana")
    holders.route_phone(Env.sandbox, "+34600000000", "m_ana")
    holders.route_phone(Env.sandbox, "+34611111111", "m_eva")
    assert holders.phones_of(Env.sandbox, "m_ana") == ["+34600000000"]
    assert holders.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]
    assert holders.forget_phones(Env.sandbox, "m_ana") == ["+34600000000"]
    assert holders.phones_of(Env.sandbox, "m_ana") == []
    assert holders.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]


# 2026-11-17, 18:18 UTC: a tenant's process restarted in 72 s, as it had four times that day, and its
# agent rang nowhere for six minutes with the process connected. The gateway its terminal had left
# pruned the line it let go after a minute and went on saying it; the other had pruned the line it
# gave and went on saying that. The new process read the stale line as held, and took none.
@needs_the_database
async def test_a_process_that_comes_back_after_the_line_was_forgotten_is_given_it(
    two_gateways: tuple[LiveParts, LiveParts], agent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, other = two_gateways
    await takes_rings(one, "app_before", agent)
    await watches(other, "terminal_before", agent)
    await until(lambda: rings_at(other, agent) == "app_before")
    await one.holders.release("app_before")
    await until(lambda: rings_at(other, agent) is None)
    await other.holders.release("terminal_before")
    await until(lambda: one.holders.line_of(Env.production, agent) is None)
    monkeypatch.setattr(shared_state, "FORGOTTEN_AFTER_S", 0.0)
    await takes_rings(other, "app_after", agent)
    await watches(one, "terminal_after", agent)
    await until(lambda: rings_at(one, agent) == "app_after" and rings_at(other, agent) == "app_after")
    assert one.holders.line_of(Env.production, agent) == THE_ORGS_OWN


# 2026-11-17, 19:44 UTC: a release rolled the gateways, the tenant's process connected again to a new
# one while the old one was still saying the line, and the line went with the old gateway.
@needs_the_database
async def test_a_line_that_goes_with_its_gateway_is_given_to_the_process_that_is_still_there(
    two_gateways: tuple[LiveParts, LiveParts], agent: str
) -> None:
    old, new = two_gateways
    await takes_rings(old, "app_before", agent)
    await until(lambda: new.holders.line_of(Env.production, agent) == THE_ORGS_OWN)
    await takes_rings(new, "app_after", agent)
    await old.holders.close()
    shared = new.holders._shared  # pyright: ignore[reportPrivateUsage]  # the old gateway falls silent
    shared.theirs.clear()
    new.holders._merge()  # pyright: ignore[reportPrivateUsage]  # as the beat does once it has
    assert rings_at(new, agent) == "app_after"


@needs_the_database
async def test_a_line_let_go_on_purpose_is_not_given_back_at_once(live: LiveParts, agent: str) -> None:
    """`line release` with nobody else to take it leaves the line with nobody, while it is remembered."""
    await takes_rings(live, "app_1", agent)
    assert live.holders.drop_line(SCOPE, agent)
    assert live.holders.line_of(Env.production, agent) is None

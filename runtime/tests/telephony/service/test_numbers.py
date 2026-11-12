"""A number let go, moved between envs, and listed from what the org's accounts own."""

import dataclasses

import pytest

from runtime.enums import Channel, Env, RouteOrigin
from runtime.exceptions import NotFound
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, number_hook, numbers
from runtime.telephony.service.number_hook import NumberImport, Plan
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from tests.conftest import make_tenant, needs_the_database
from tests.telephony.conftest import Line, a_number

pytestmark = needs_the_database


async def imported(line: Line, wanted: NumberImport) -> Plan:
    """The import, in one transaction as the endpoint runs it."""
    async with line.sessions.begin() as session:
        return await number_hook.import_number(session, line.vault, line.http, line.livekits, line.names, wanted)


async def moved(line: Line, number: str, env: Env) -> RouteToWrite | None:
    """The org's number moved into the env, as the endpoint moves it."""
    async with line.sessions.begin() as session:
        route = await numbers.get_number(session, line.org, number)
        done = await numbers.move_number(session, line.vault, line.livekits, route, env)
        return RouteToWrite(
            org=done.org, number=done.number, agent=done.agent, channel=done.channel, env=done.env, origin=done.origin
        )


# ── letting go, moving between envs ──


async def test_letting_a_number_go_removes_the_route_and_the_admission_but_not_the_carrier(line: Line) -> None:
    """Released, the row, the trunk and the rule go; the number stays on its Twilio trunk."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", number))
    async with line.sessions.begin() as session:
        route = await numbers.get_number(session, line.org, number, Env.production)
        await numbers.release_number(session, line.livekits, route)
    async with line.sessions() as session:
        assert await RouteRepository(session).find(line.org, number) is None
    assert line.servers[Env.production].dialled.trunks == {}
    assert line.rules() == []
    assert line.twilio.numbers[number][1] is not None
    async with line.sessions() as session:
        with pytest.raises(NotFound):
            await numbers.get_number(session, line.org, number, Env.production)


async def test_a_number_moved_between_envs_leaves_one_livekit_and_lands_on_the_other(line: Line) -> None:
    """Moved, the number is on the new env's LiveKit alone, there and back."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    there = await moved(line, number, Env.sandbox)
    assert there is not None and (there.env, there.origin) == (Env.sandbox, RouteOrigin.hooked)
    production = line.servers[Env.production].dialled
    assert production.trunks == production.rules == {}
    assert list(line.trunk(line.org, Env.sandbox).numbers) == [number]
    assert list(line.rule(Env.sandbox).numbers) == [number]
    back = await moved(line, number, Env.production)
    assert back is not None and back.env is Env.production
    assert line.servers[Env.sandbox].dialled.trunks == {}
    assert list(line.rule(Env.production).numbers) == [number]


async def test_where_both_envs_share_a_livekit_a_number_moves_between_rules_not_trunks(line: Line) -> None:
    """On one LiveKit the trunk stays as it was and the number changes rules."""
    number = a_number()
    shared = line.servers[Env.production]
    one = dataclasses.replace(line, servers={Env.production: shared, Env.sandbox: shared})
    await imported(one, NumberImport(one.scope(), "recepcion", number, hooked=True))
    trunks = dict(shared.dialled.trunks)
    await moved(one, number, Env.sandbox)
    (rule,) = shared.dialled.rules.values()
    assert (rule.name, list(rule.numbers)) == (f"{line.org}:sandbox", [number])
    assert shared.dialled.trunks == trunks


async def test_a_whatsapp_number_moves_env_by_its_row_and_nothing_lands_on_the_sfu(line: Line) -> None:
    """A WhatsApp number is on no trunk: moving it is its row alone."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp, hooked=True))
    there = await moved(line, number, Env.sandbox)
    assert there is not None and (there.channel, there.env) == (Channel.whatsapp, Env.sandbox)
    assert all(server.dialled.trunks == {} for server in line.servers.values())
    assert line.rules(Env.production) == line.rules(Env.sandbox) == []


# ── what the accounts own ──


async def test_what_the_account_owns_is_every_page_and_says_which_this_env_imported(line: Line) -> None:
    """Every page of the account's numbers is read, each marked imported only in the env that did."""
    owned_here = [a_number() for _ in range(5)]
    await line.brought()
    line.twilio.page_size = 2
    for number in owned_here:
        line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", owned_here[2]))
    async with line.sessions() as session:
        here = await numbers.list_owned(session, line.vault, line.http, line.scope())
        in_the_sandbox = await numbers.list_owned(session, line.vault, line.http, line.scope(Env.sandbox))
    assert (here.kind, len(here.numbers)) == ("twilio", 5)
    assert [item.number for item in here.numbers if item.imported] == [owned_here[2]]
    assert not any(item.imported for item in in_the_sandbox.numbers)


async def test_what_the_account_owns_says_which_number_another_org_holds(line: Line) -> None:
    """A number another org routes cannot be imported here: the list says so instead of 'not routed here'."""
    mine, theirs = a_number(), a_number()
    await line.brought()
    line.twilio.owns(mine)
    line.twilio.owns(theirs)
    other = await make_tenant(line.sessions)
    held = RouteToWrite(org=other.org, number=theirs, agent="agenda", channel=Channel.phone, env=Env.production)
    async with line.sessions.begin() as session:
        await RouteRepository(session).put(held)
    async with line.sessions() as session:
        owned = await numbers.list_owned(session, line.vault, line.http, line.scope())
    assert {item.number: item.held_elsewhere for item in owned.numbers} == {mine: False, theirs: True}


async def test_an_account_taken_back_leaves_its_numbers_routed(line: Line) -> None:
    """Forgetting the account leaves its numbers answering until each is let go."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", number))
    async with line.sessions.begin() as session:
        await accounts.delete_carrier(session, line.vault, line.org)
    async with line.sessions() as session:
        listed = await RouteRepository(session).list_of_org(line.org, Env.production)
        assert [one.route.number for one in listed] == [number]
        with pytest.raises(NotFound, match="no carrier account"):
            await accounts.get_carrier(session, line.vault, line.org)


async def test_a_whatsapp_accounts_number_is_listed_from_meta_and_imported_on_the_account(line: Line) -> None:
    """Meta says which number the account is; imported, it is a row alone; a dead token lists nothing."""
    number = line.graph.number
    async with line.sessions.begin() as session:
        at_meta = WhatsappNumber(org=line.org, phone_number_id="1055", access_token="the org's")
        await accounts.put_carrier(session, line.vault, at_meta)
    async with line.sessions() as session:
        owned = await numbers.list_owned(session, line.vault, line.http, line.scope())
    assert owned.kind == "whatsapp"
    assert [(item.number, item.name, item.account, item.imported) for item in owned.numbers] == [
        (number, "Clinica", "1055", False)
    ]
    plan = await imported(
        line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp, account="1055")
    )
    assert plan.steps == [f"route: {number} to recepcion in the production: done"]
    async with line.sessions() as session:
        assert (await numbers.list_owned(session, line.vault, line.http, line.scope())).numbers[0].imported
        line.graph.refusal = (401, "Session has expired")
        assert (await numbers.list_owned(session, line.vault, line.http, line.scope())).numbers == []

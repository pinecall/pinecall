"""A number let go, moved between envs, and listed from what the org's accounts own."""

import dataclasses

import pytest

from runtime.enums import Channel, Env, RouteOrigin
from runtime.exceptions import Conflict, NotFound
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, number_hook, number_path, numbers, routes
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
        assert await RouteRepository(session).list_at(line.org, number) == []
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


# ── one number, more than one channel ──


async def test_a_number_answers_the_phone_and_whatsapp_at_once_and_each_is_let_go_alone(line: Line) -> None:
    """Importing a phone number as WhatsApp adds a route and leaves the phone's as it was, trunk and all."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    trunk = list(line.trunk(line.org, Env.production).numbers)
    await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.whatsapp, hooked=True))
    async with line.sessions.begin() as session:
        both = await RouteRepository(session).list_at(line.org, number)
        assert [(one.route.channel, one.route.agent) for one in both] == [
            (Channel.phone, "recepcion"),
            (Channel.whatsapp, "front-desk"),
        ]
        with pytest.raises(Conflict, match="answers on phone and whatsapp"):
            await numbers.get_number(session, line.org, number)
        written = await numbers.get_number(session, line.org, number, channel=Channel.whatsapp)
        await numbers.release_number(session, line.livekits, written)
    assert list(line.trunk(line.org, Env.production).numbers) == trunk == [number]
    async with line.sessions() as session:
        (left,) = await RouteRepository(session).list_at(line.org, number)
        assert (left.route.channel, left.route.agent) == (Channel.phone, "recepcion")
        assert (await numbers.get_number(session, line.org, number)).channel is Channel.phone


# ── what the accounts own ──


async def rings(line: Line, number: str, channel: Channel) -> tuple[str, bool]:
    """What the number does on the channel, its agent running, and whether anything is noted to have reached it."""
    async with line.sessions() as session:
        route = await numbers.get_number(session, line.org, number, channel=channel)
        (state,) = await number_path.rings_of(session, line.vault, [route], lambda _: True)
        return state, route.last_call_at is not None


async def test_a_message_is_noted_on_its_own_channel_and_the_number_stops_waiting(line: Line) -> None:
    """Until 2026-11-19 a call alone was noted: a number written to waited for its first message for ever."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "front-desk", number, channel=Channel.whatsapp, hooked=True))
    assert await rings(line, number, Channel.whatsapp) == ("waiting", False)
    async with line.sessions.begin() as session:
        await routes.note_call(session, line.org, number)
    assert await rings(line, number, Channel.whatsapp) == ("waiting", False), "a call is not a message to it"
    async with line.sessions.begin() as session:
        await routes.note_call(session, line.org, number, Channel.whatsapp)
    assert await rings(line, number, Channel.whatsapp) == ("ok", True)


async def test_a_mailbox_is_read_by_the_box_and_waits_for_nothing(line: Line) -> None:
    """The box reads the mailbox itself, with the login it checked: it reaches us before its first email."""
    address = f"help-{a_number()[1:]}@acme.example"
    mailbox = RouteToWrite(org=line.org, number=address, agent="front-desk", channel=Channel.email, env=Env.production)
    async with line.sessions.begin() as session:
        await RouteRepository(session).put(mailbox)
    assert await rings(line, address, Channel.email) == ("ok", False)
    async with line.sessions.begin() as session:
        await routes.note_call(session, line.org, address, Channel.email)
    assert await rings(line, address, Channel.email) == ("ok", True)


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

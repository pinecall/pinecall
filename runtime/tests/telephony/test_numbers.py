"""A number imported, bought, released and moved: at the carrier, on each env's LiveKit, in the routes."""

from dataclasses import replace

import pytest
from livekit.protocol.sip import CreateSIPInboundTrunkRequest, SIPInboundTrunkInfo

from pinecall_runtime.channels.models import Route
from pinecall_runtime.channels.service.routes import RouteWrite, get_route, managed_in, put_route, routes_of_org
from pinecall_runtime.enums import Channel, Env, NetworkState, RouteOrigin
from pinecall_runtime.exceptions import Conflict, NotFound, ServiceUnavailable
from pinecall_runtime.telephony.schemas import WhatsappAccount
from pinecall_runtime.telephony.service import accounts, networks, sip
from pinecall_runtime.telephony.service.fence import TWILIO_SIGNALLING
from pinecall_runtime.telephony.service.numbers import (
    NumberImport,
    NumberPurchase,
    Plan,
    buy_number,
    import_number,
    move_number,
    owned_numbers,
    plan_buy,
    plan_import,
    release_number,
    type_route,
)
from pinecall_runtime.telephony.service.records import record_of
from pinecall_runtime.telephony.service.twilio import origination_uri
from tests.conftest import make_tenant, needs_the_database
from tests.telephony.conftest import DOMAIN, Line, a_number

pytestmark = needs_the_database

HERE = origination_uri(DOMAIN)


async def imported(line: Line, wanted: NumberImport) -> Plan:
    """The import, in one transaction as the endpoint runs it."""
    async with line.sessions.begin() as session:
        return await import_number(session, line.handles, wanted)


async def origin_of(line: Line, number: str) -> RouteOrigin | None:
    """How the org's row at the number was written; None with no row."""
    async with line.sessions() as session:
        record = await record_of(session, line.org, number)
    return None if record is None else record.route.origin


# ── importing: at the carrier, on the SFU, in the table ──


async def test_an_import_makes_the_trunk_attaches_admits_rules_and_routes_once(line: Line) -> None:
    """Every step is done the first time and stands the second; the other env's LiveKit is untouched."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    plan = await imported(line, NumberImport(line.scope(Env.sandbox), "recepcion", number))
    assert not plan.dry_run
    assert all(step.endswith("done") for step in plan.steps)
    (trunk,) = line.twilio.trunks.values()
    assert trunk.origination == [HERE]
    assert line.twilio.numbers[number][1] == trunk.sid
    sfu = line.trunk(line.org, Env.sandbox)
    assert (list(sfu.numbers), list(sfu.allowed_addresses)) == ([number], list(TWILIO_SIGNALLING))
    rule = line.rule(Env.sandbox)
    assert list(rule.numbers) == [number]
    assert [agent.agent_name for agent in rule.room_config.agents] == ["pinecall-sandbox"]
    async with line.sessions() as session:
        routed = await get_route(session, line.org, number)
    assert routed is not None
    assert (routed.agent, routed.env, routed.managed, routed.origin) == (
        "recepcion",
        Env.sandbox,
        False,
        RouteOrigin.imported,
    )
    again = await imported(line, NumberImport(line.scope(Env.sandbox), "recepcion", number))
    assert all(step.endswith("stands") for step in again.steps)
    assert len(line.twilio.trunks) == 1
    sandbox, production = line.servers[Env.sandbox].dialled, line.servers[Env.production].dialled
    assert len(sandbox.trunks) == len(sandbox.rules) == 1
    assert production.trunks == production.rules == {}, "the sandbox's alone"


async def test_a_dry_run_is_the_plan_and_writes_nothing_anywhere(line: Line) -> None:
    """Planned, nothing changes at Twilio, on either LiveKit or in the table."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    async with line.sessions.begin() as session:
        plan = await plan_import(session, line.handles, NumberImport(line.scope(), "recepcion", number))
    assert plan.dry_run
    assert all(step.endswith("to do") for step in plan.steps)
    assert line.twilio.written() == []
    assert all(server.dialled.trunks == {} for server in line.servers.values())
    assert await origin_of(line, number) is None


async def test_a_number_on_another_trunk_of_the_account_is_refused_naming_it_until_moved(line: Line) -> None:
    """Taking a number off a trunk pointed elsewhere is said out loud: refused naming it, done when asked."""
    number = a_number()
    await line.brought()
    old = line.twilio.trunk("pinecall-org_1", "sip:old.box.test:5060")
    line.twilio.owns(number, trunk=old)
    with pytest.raises(Conflict, match=r"pinecall-org_1.*old\.box\.test.*move"):
        await imported(line, NumberImport(line.scope(), "recepcion", number))
    assert line.twilio.numbers[number][1] == old
    await imported(line, NumberImport(line.scope(), "recepcion", number, move=True))
    sid, now = line.twilio.numbers[number]
    assert now not in {None, old}
    assert ("DELETE", f"/v1/Trunks/{old}/PhoneNumbers/{sid}") in line.twilio.requests


async def test_a_number_the_account_does_not_own_is_refused_before_anything_is_written(line: Line) -> None:
    """A number of no account of the org's is not found, and Twilio is never written to."""
    await line.brought()
    with pytest.raises(NotFound, match="not a number of Twilio account"):
        await imported(line, NumberImport(line.scope(), "recepcion", a_number()))
    assert line.twilio.written() == []


async def test_a_number_another_orgs_trunk_lists_is_refused_naming_nobody(line: Line) -> None:
    """Another org's trunk on the SFU holds the number: refused before Twilio is written, its name kept."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    their_trunk = SIPInboundTrunkInfo(name="org_other", numbers=[number])
    await line.servers[Env.production].sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=their_trunk))
    with pytest.raises(Conflict, match="held by another org") as refused:
        await imported(line, NumberImport(line.scope(), "recepcion", number))
    assert "org_other" not in str(refused.value)
    assert line.twilio.written() == []


async def test_a_number_another_org_routes_is_refused_before_the_sfu_is_asked(line: Line) -> None:
    """One org holds a number on the box: another org's row refuses the import, naming nobody."""
    number = a_number()
    other = await make_tenant(line.sessions)
    theirs = Route(org=other.org, agent="agenda", channel=Channel.phone, number=number, env=Env.production)
    async with line.sessions.begin() as session:
        await put_route(session, theirs, RouteWrite(origin=RouteOrigin.typed))
    with pytest.raises(Conflict, match="held by another org") as refused:
        await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    assert other.org not in str(refused.value)
    assert line.servers[Env.production].dialled.requests == [], "the SFU is never asked"


async def test_a_number_the_org_hooks_itself_waits_for_its_networks_then_gets_its_own_fence(line: Line) -> None:
    """Its own networks wait for the operator; approved, a trunk of the number's own admits them alone."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True, networks=("45.60.13.7",)))
    assert line.servers[Env.production].dialled.trunks == {}
    async with line.sessions.begin() as session:
        (ask,) = await networks.of_org(session, line.org)
        assert (ask.source, ask.network, ask.state) == (number, "45.60.13.7/32", NetworkState.waiting)
        await networks.decide(session, ask.id, NetworkState.approved, "ana@pinecall.test")
    async with line.sessions.begin() as session:
        assert await sip.readmit(session, line.handles, line.org) == 1
    assert list(line.trunk(f"{line.org}:{number}").allowed_addresses) == ["45.60.13.7/32"]
    await imported(line, NumberImport(line.scope(), "recepcion", a_number(), hooked=True))
    assert list(line.trunk(line.org).allowed_addresses) == list(TWILIO_SIGNALLING), "no networks: Twilio's"


async def test_a_box_with_no_name_cannot_be_pointed_at(line: Line) -> None:
    """With no PINECALL_DOMAIN a carrier has nowhere to send a call, and the import says so."""
    nameless = replace(line.handles, settings=line.handles.settings.model_copy(update={"domain": None}))
    async with line.sessions.begin() as session:
        with pytest.raises(ServiceUnavailable, match="PINECALL_DOMAIN"):
            await import_number(session, nameless, NumberImport(line.scope(), "recepcion", a_number(), hooked=True))


async def test_a_number_imported_again_in_the_other_env_leaves_the_first_envs_livekit(line: Line) -> None:
    """A number lives on one LiveKit: imported into the sandbox, production's trunk and rule let it go."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    in_the_sandbox = NumberImport(line.scope(Env.sandbox), "recepcion", number, hooked=True)
    async with line.sessions.begin() as session:
        again = await plan_import(session, line.handles, in_the_sandbox)
    assert f"LiveKit of the production: {number} off trunk {line.org}: to do" in again.steps
    await imported(line, in_the_sandbox)
    assert (line.rules(Env.production), line.rules(Env.sandbox)) == ([], [f"{line.org}:sandbox"])
    assert list(line.rule(Env.sandbox).numbers) == [number]
    assert line.servers[Env.production].dialled.trunks == {}


async def test_an_operators_route_is_admitted_at_once_and_touches_no_account(line: Line) -> None:
    """A route the box's operator types is on the SFU at once, written as typed, Twilio never asked."""
    number = a_number()
    await line.brought()
    asked = len(line.twilio.requests)
    async with line.sessions.begin() as session:
        typed = await type_route(
            session, line.handles, NumberImport(line.scope(), "recepcion", number, account="ignored")
        )
    assert not any(step.startswith("Twilio") for step in typed.steps)
    assert len(line.twilio.requests) == asked
    assert list(line.trunk(line.org).numbers) == [number]
    assert list(line.rule(Env.production).numbers) == [number]
    assert await origin_of(line, number) is RouteOrigin.typed


# ── letting go, moving between envs ──


async def test_letting_a_number_go_removes_the_route_and_the_admission_but_not_the_carrier(line: Line) -> None:
    """Released, the row, the trunk and the rule go; the number stays on its Twilio trunk."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", number))
    async with line.sessions.begin() as session:
        await release_number(session, line.handles, line.org, number, Env.production)
    assert await origin_of(line, number) is None
    assert line.servers[Env.production].dialled.trunks == {}
    assert line.rules() == []
    assert line.twilio.numbers[number][1] is not None
    async with line.sessions.begin() as session:
        with pytest.raises(NotFound):
            await release_number(session, line.handles, line.org, number, Env.production)


async def test_a_number_moved_between_envs_leaves_one_livekit_and_lands_on_the_other(line: Line) -> None:
    """Moved, the number is on the new env's LiveKit alone, there and back."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    async with line.sessions.begin() as session:
        moved = await move_number(session, line.handles, line.org, number, Env.sandbox)
    assert (moved.env, moved.origin) == (Env.sandbox, RouteOrigin.hooked)
    production = line.servers[Env.production].dialled
    assert production.trunks == production.rules == {}
    assert list(line.trunk(line.org, Env.sandbox).numbers) == [number]
    assert list(line.rule(Env.sandbox).numbers) == [number]
    async with line.sessions.begin() as session:
        back = await move_number(session, line.handles, line.org, number, Env.production)
    assert back.env is Env.production
    assert line.servers[Env.sandbox].dialled.trunks == {}
    assert list(line.rule(Env.production).numbers) == [number]


async def test_where_both_envs_share_a_livekit_a_number_moves_between_rules_not_trunks(line: Line) -> None:
    """On one LiveKit the trunk stays as it was and the number changes rules."""
    number = a_number()
    shared = line.servers[Env.production]
    one = replace(line.handles, servers={Env.production: shared, Env.sandbox: shared})
    async with line.sessions.begin() as session:
        await import_number(session, one, NumberImport(line.scope(), "recepcion", number, hooked=True))
    trunks = dict(shared.dialled.trunks)
    async with line.sessions.begin() as session:
        await move_number(session, one, line.org, number, Env.sandbox)
    (rule,) = shared.dialled.rules.values()
    assert (rule.name, list(rule.numbers)) == (f"{line.org}:sandbox", [number])
    assert shared.dialled.trunks == trunks


async def test_a_whatsapp_number_moves_env_by_its_row_and_nothing_lands_on_the_sfu(line: Line) -> None:
    """A WhatsApp number is on no trunk: moving it is its row alone."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp, hooked=True))
    async with line.sessions.begin() as session:
        moved = await move_number(session, line.handles, line.org, number, Env.sandbox)
    assert (moved.channel, moved.env) == (Channel.whatsapp, Env.sandbox)
    assert all(server.dialled.trunks == {} for server in line.servers.values())
    assert line.rules(Env.production) == line.rules(Env.sandbox) == []


# ── buying on the box's account ──


async def test_a_purchase_is_planned_without_buying_then_bought_attached_and_routed_as_the_boxs(line: Line) -> None:
    """A dry purchase names the number and buys nothing; the purchase hooks it, counted as the box's."""
    number = a_number()
    async with line.sessions.begin() as session:
        await accounts.put_box_twilio(session, line.handles.vault, line.account())
    line.twilio.for_sale = [number]
    wanted = NumberPurchase(line.scope(Env.sandbox), "recepcion", "us")
    async with line.sessions.begin() as session:
        plan = await plan_buy(session, line.handles, wanted)
    assert (plan.route.number, number in plan.steps[0]) == (number, True)
    assert (line.twilio.written(), line.twilio.for_sale) == ([], [number])
    async with line.sessions.begin() as session:
        bought = await buy_number(session, line.handles, wanted)
    assert bought.route.managed
    assert line.twilio.numbers[number][1] is not None
    assert list(line.rule(Env.sandbox).numbers) == [number]
    async with line.sessions() as session:
        assert await managed_in(session, line.org, Env.sandbox) == 1
    assert await origin_of(line, number) is RouteOrigin.bought


async def test_nothing_for_sale_there_is_not_found_in_our_words(line: Line) -> None:
    """Twilio selling nothing in the area is said in a sentence of ours."""
    async with line.sessions.begin() as session:
        await accounts.put_box_twilio(session, line.handles.vault, line.account())
    async with line.sessions.begin() as session:
        with pytest.raises(NotFound, match="no local voice number for sale in US, area code 212"):
            await buy_number(session, line.handles, NumberPurchase(line.scope(), "recepcion", "us", "212"))


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
        kind, owned = await owned_numbers(session, line.handles, line.scope())
        _, in_the_sandbox = await owned_numbers(session, line.handles, line.scope(Env.sandbox))
    assert (kind, len(owned)) == ("twilio", 5)
    assert [item.number for item in owned if item.imported] == [owned_here[2]]
    assert not any(item.imported for item in in_the_sandbox)


async def test_an_account_taken_back_leaves_its_numbers_routed(line: Line) -> None:
    """Forgetting the account leaves its numbers answering until each is let go."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    await imported(line, NumberImport(line.scope(), "recepcion", number))
    async with line.sessions.begin() as session:
        await accounts.drop_carrier(session, line.handles.vault, line.org)
    async with line.sessions() as session:
        assert [route.number for route in await routes_of_org(session, line.org, Env.production)] == [number]
        with pytest.raises(NotFound, match="no carrier account"):
            await accounts.carrier_named(session, line.handles.vault, line.org)


async def test_a_whatsapp_accounts_number_is_listed_from_meta_and_imported_on_the_account(line: Line) -> None:
    """Meta says which number the account is; imported, it is a row alone; a dead token lists nothing."""
    number = line.graph.number
    at_meta = WhatsappAccount.model_validate({"phone_number_id": "1055", "access_token": "the org's"})
    async with line.sessions.begin() as session:
        await accounts.put_carrier(session, line.handles.vault, line.org, at_meta)
    async with line.sessions() as session:
        kind, owned = await owned_numbers(session, line.handles, line.scope())
    assert kind == "whatsapp"
    assert [(item.number, item.name, item.account, item.imported) for item in owned] == [
        (number, "Clinica", "1055", False)
    ]
    plan = await imported(
        line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp, account="1055")
    )
    assert plan.steps == [f"route: {number} to recepcion in the production: done"]
    async with line.sessions() as session:
        assert (await owned_numbers(session, line.handles, line.scope()))[1][0].imported
        line.graph.refusal = (401, "Session has expired")
        assert (await owned_numbers(session, line.handles, line.scope()))[1] == []

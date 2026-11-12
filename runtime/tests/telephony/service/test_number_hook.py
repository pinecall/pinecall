"""A number imported, typed or bought: at the carrier, on each env's LiveKit, in the routes."""

import dataclasses
import re

import pytest
from livekit.protocol.sip import CreateSIPInboundTrunkRequest, SIPInboundTrunkInfo
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Channel, Env, RouteOrigin
from runtime.exceptions import Conflict, NotFound, ServiceUnavailable, ValidationError
from runtime.postgres import BoxSession
from runtime.telephony.models import NetworkState
from runtime.telephony.repository import RouteRepository, RouteToWrite
from runtime.telephony.service import accounts, networks, number_hook, rebuild
from runtime.telephony.service.carrier import origination_uri
from runtime.telephony.service.fence import TWILIO_SIGNALLING
from runtime.telephony.service.number_hook import NumberImport, NumberPurchase, Plan
from runtime.telephony.service.whatsapp_number import WhatsappNumber
from tests.conftest import make_tenant, needs_the_database
from tests.telephony.conftest import DOMAIN, Line, a_number

pytestmark = needs_the_database

HERE = origination_uri(DOMAIN)


async def imported(line: Line, wanted: NumberImport) -> Plan:
    """The import, in one transaction as the endpoint runs it."""
    async with line.sessions.begin() as session:
        return await number_hook.import_number(session, line.vault, line.http, line.livekits, line.names, wanted)


async def planned(line: Line, wanted: NumberImport) -> Plan:
    """The import's plan, nothing written."""
    async with line.sessions.begin() as session:
        return await number_hook.plan_import(session, line.vault, line.http, line.livekits, line.names, wanted)


async def origin_of(line: Line, number: str) -> RouteOrigin | None:
    """How the org's row at the number was written; None with no row."""
    async with line.sessions() as session:
        found = await RouteRepository(session).find(line.org, number)
    return None if found is None else found.route.origin


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
        routed = await RouteRepository(session).find(line.org, number)
    assert routed is not None
    assert (routed.route.agent, routed.route.env, routed.route.managed, routed.route.origin) == (
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
    plan = await planned(line, NumberImport(line.scope(), "recepcion", number))
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
    theirs = RouteToWrite(org=other.org, number=number, agent="agenda", channel=Channel.phone, env=Env.production)
    async with line.sessions.begin() as session:
        await RouteRepository(session).put(theirs)
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
        (ask,) = await networks.list_of_org(session, line.org)
        assert (ask.source, str(ask.network), ask.state) == (number, "45.60.13.7/32", NetworkState.waiting)
        await networks.decide(session, ask.id, NetworkState.approved, "ana@pinecall.test")
    async with line.sessions.begin() as session:
        assert await rebuild.readmit(session, line.vault, line.livekits, line.org) == 1
    assert list(line.trunk(f"{line.org}:{number}").allowed_addresses) == ["45.60.13.7/32"]
    await imported(line, NumberImport(line.scope(), "recepcion", a_number(), hooked=True))
    assert list(line.trunk(line.org).allowed_addresses) == list(TWILIO_SIGNALLING), "no networks: Twilio's"


async def test_a_box_with_no_name_cannot_be_pointed_at(line: Line) -> None:
    """With no PINECALL_DOMAIN a carrier has nowhere to send a call, and the import says so."""
    nameless = dataclasses.replace(line.names, domain=None, sip_domains={})
    wanted = NumberImport(line.scope(), "recepcion", a_number(), hooked=True)
    async with line.sessions.begin() as session:
        with pytest.raises(ServiceUnavailable, match="PINECALL_DOMAIN"):
            await number_hook.import_number(session, line.vault, line.http, line.livekits, nameless, wanted)


async def test_a_number_imported_again_in_the_other_env_leaves_the_first_envs_livekit(line: Line) -> None:
    """A number lives on one LiveKit: imported into the sandbox, production's trunk and rule let it go."""
    number = a_number()
    await imported(line, NumberImport(line.scope(), "recepcion", number, hooked=True))
    in_the_sandbox = NumberImport(line.scope(Env.sandbox), "recepcion", number, hooked=True)
    again = await planned(line, in_the_sandbox)
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
    wanted = NumberImport(line.scope(), "recepcion", number, account="ignored")
    async with line.sessions.begin() as session:
        typed = await number_hook.type_route(session, line.vault, line.http, line.livekits, line.names, wanted)
    assert not any(step.startswith("Twilio") for step in typed.steps)
    assert len(line.twilio.requests) == asked
    assert list(line.trunk(line.org).numbers) == [number]
    assert list(line.rule(Env.production).numbers) == [number]
    assert await origin_of(line, number) is RouteOrigin.typed


async def test_a_phone_number_is_not_imported_as_a_whatsapp_route(line: Line) -> None:
    """A WhatsApp route is the number a WhatsApp Business account is, never a phone number renamed."""
    number = a_number()
    await line.brought()
    line.twilio.owns(number)
    with pytest.raises(ValidationError, match="comes through the org's WhatsApp Business account"):
        await imported(line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp))
    async with line.sessions.begin() as session:
        at_meta = WhatsappNumber(org=line.org, phone_number_id="1055", access_token="the org's")
        await accounts.put_carrier(session, line.vault, at_meta)
    with pytest.raises(ValidationError, match=re.escape(f"Meta says it is {line.graph.number}")):
        await imported(line, NumberImport(line.scope(), "recepcion", number, channel=Channel.whatsapp, account="1055"))
    async with line.sessions() as session:
        assert list(await RouteRepository(session).list_of_org(line.org, Env.production)) == []


# ── buying on the box's account ──


async def on_the_boxs_account(line: Line, session: AsyncSession) -> None:
    """The box buys numbers on the fake Twilio account."""
    await accounts.put_box_twilio(BoxSession(session), line.vault, line.http, line.account().account)


async def test_a_purchase_is_planned_without_buying_then_bought_attached_and_routed_as_the_boxs(line: Line) -> None:
    """A dry purchase names the number and buys nothing; the purchase hooks it, counted as the box's."""
    number = a_number()
    async with line.sessions.begin() as session:
        await on_the_boxs_account(line, session)
    try:
        line.twilio.for_sale = [number]
        wanted = NumberPurchase(line.scope(Env.sandbox), "recepcion", "us")
        async with line.sessions.begin() as session:
            plan = await number_hook.plan_buy(session, line.vault, line.http, line.livekits, line.names, wanted)
        assert (plan.route.number, number in plan.steps[0]) == (number, True)
        assert (line.twilio.written(), line.twilio.for_sale) == ([], [number])
        async with line.sessions.begin() as session:
            bought = await number_hook.buy_number(session, line.vault, line.http, line.livekits, line.names, wanted)
        assert bought.route.managed
        assert line.twilio.numbers[number][1] is not None
        assert list(line.rule(Env.sandbox).numbers) == [number]
        async with line.sessions() as session:
            assert await RouteRepository(session).count_managed(line.org, Env.sandbox) == 1
        assert await origin_of(line, number) is RouteOrigin.bought
    finally:
        async with line.sessions.begin() as session:
            await accounts.delete_box_twilio(BoxSession(session))


async def test_nothing_for_sale_there_is_not_found_in_our_words(line: Line) -> None:
    """Twilio selling nothing in the area is said in a sentence of ours."""
    async with line.sessions.begin() as session:
        await on_the_boxs_account(line, session)
    try:
        wanted = NumberPurchase(line.scope(), "recepcion", "us", "212")
        async with line.sessions.begin() as session:
            with pytest.raises(NotFound, match="no local voice number for sale in US, area code 212"):
                await number_hook.buy_number(session, line.vault, line.http, line.livekits, line.names, wanted)
    finally:
        async with line.sessions.begin() as session:
            await accounts.delete_box_twilio(BoxSession(session))

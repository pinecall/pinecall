"""The SFU's side of a number: LiveKit's inbound trunks, one per fence, and its dispatch rules, one per org and env."""

from collections.abc import Sequence
from dataclasses import dataclass

from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration
from livekit.protocol.sip import (
    CreateSIPDispatchRuleRequest,
    CreateSIPInboundTrunkRequest,
    DeleteSIPDispatchRuleRequest,
    DeleteSIPTrunkRequest,
    ListSIPDispatchRuleRequest,
    ListSIPInboundTrunkRequest,
    SIPDispatchRule,
    SIPDispatchRuleIndividual,
    SIPDispatchRuleInfo,
    SIPInboundTrunkInfo,
)

from runtime.enums import Env
from runtime.livekit import Servers
from runtime.telephony.service.fence import Fence
from runtime.wire.dispatch import Dispatch

ROOM_PREFIX = "call-"


@dataclass(frozen=True, slots=True)
class EnvRule:
    """An org's env on the SFU: its rule, and the fleet the rule dispatches."""

    org: str
    env: Env
    fleet: str


# Both envs hold the one client when the sandbox has no LiveKit of its own.
def other_server(servers: Servers, env: Env) -> api.LiveKitAPI | None:
    """The other env's LiveKit when it is not this env's too; None where both share one."""
    other = servers[env.other]
    return None if other is servers[env] else other


def rule_name(org: str, env: Env) -> str:
    """The name of an org's dispatch rule in an env."""
    return f"{org}:{env}"


# An org id holds no colon, so `{org}` and `{org}:…` can never be another org's.
def belongs_to(name: str, org: str) -> bool:
    """Whether a trunk or rule name is the org's."""
    return name == org or name.startswith(f"{org}:")


async def list_trunks_admitting(server: api.LiveKitAPI, number: str) -> list[SIPInboundTrunkInfo]:
    """Every trunk on the SFU that lists the number."""
    listed = await server.sip.list_inbound_trunk(ListSIPInboundTrunkRequest(numbers=[number]))
    return [trunk for trunk in listed.items if number in trunk.numbers]


async def find_trunk(server: api.LiveKitAPI, name: str) -> SIPInboundTrunkInfo | None:
    """The trunk of that name, or None."""
    listed = await server.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
    return next((trunk for trunk in listed.items if trunk.name == name), None)


async def list_rules(server: api.LiveKitAPI) -> list[SIPDispatchRuleInfo]:
    """Every dispatch rule on the SFU."""
    return list((await server.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())).items)


async def find_rule(server: api.LiveKitAPI, name: str) -> SIPDispatchRuleInfo | None:
    """The dispatch rule of that name, or None."""
    return next((rule for rule in await list_rules(server) if rule.name == name), None)


def admits(trunk: SIPInboundTrunkInfo | None, fence: Fence, number: str) -> bool:
    """Whether the trunk lists the number behind exactly this fence: admitting it again would write nothing."""
    if trunk is None:
        return False
    fenced = sorted(trunk.allowed_addresses) == sorted(fence.networks)
    return number in trunk.numbers and fenced and trunk.auth_username == fence.username


async def admit(server: api.LiveKitAPI, fence: Fence, existing: SIPInboundTrunkInfo | None, number: str) -> str:
    """Make the fence's trunk list the number, made or updated; its id."""
    if existing is None:
        info = SIPInboundTrunkInfo(
            name=fence.trunk,
            numbers=[number],
            allowed_addresses=list(fence.networks),
            auth_username=fence.username,
            auth_password=fence.password,
        )
        made = await server.sip.create_inbound_trunk(CreateSIPInboundTrunkRequest(trunk=info))
        return made.sip_trunk_id
    if admits(existing, fence, number):
        return existing.sip_trunk_id
    existing.numbers[:] = sorted({*existing.numbers, number})
    existing.allowed_addresses[:] = list(fence.networks)
    existing.auth_username, existing.auth_password = fence.username, fence.password
    await server.sip.update_inbound_trunk(existing.sip_trunk_id, existing)
    return existing.sip_trunk_id


# A trunk or a rule that lists no number takes every number: one emptied is deleted, and so is
# a rule left with no trunk.
async def renumber_trunk(server: api.LiveKitAPI, org: str, trunk: SIPInboundTrunkInfo, numbers: list[str]) -> None:
    """Leave the trunk these numbers; emptied, it goes, and so does a rule left with no trunk."""
    if numbers:
        await server.sip.update_inbound_trunk_fields(trunk.sip_trunk_id, numbers=numbers)
        return
    await server.sip.delete_trunk(DeleteSIPTrunkRequest(sip_trunk_id=trunk.sip_trunk_id))
    for rule in await list_rules(server):
        if not belongs_to(rule.name, org) or trunk.sip_trunk_id not in rule.trunk_ids:
            continue
        kept = [trunk_id for trunk_id in rule.trunk_ids if trunk_id != trunk.sip_trunk_id]
        if not kept:
            await renumber_rule(server, rule, [])
            continue
        rule.trunk_ids[:] = kept
        await server.sip.update_dispatch_rule(rule.sip_dispatch_rule_id, rule)


def rules_in(rule: SIPDispatchRuleInfo | None, env_rule: EnvRule, trunks: Sequence[str], number: str) -> bool:
    """Whether the env's rule lists the number and the trunks and sends them to the fleet already."""
    if rule is None:
        return False
    fleets = [agent.agent_name for agent in rule.room_config.agents]
    return number in rule.numbers and set(trunks) <= set(rule.trunk_ids) and fleets == [env_rule.fleet]


# One rule per env: its `numbers` are that env's, so a number changes env between two lists and
# never between trunks. livekit refuses two rules of one trunk listing one number.
async def rule_in(server: api.LiveKitAPI, env_rule: EnvRule, trunks: Sequence[str], number: str) -> None:
    """Have the env's rule list the number and the trunks, made or updated."""
    # A rule with no trunk dispatches every trunk's calls.
    if not trunks:
        return
    name = rule_name(env_rule.org, env_rule.env)
    existing = await find_rule(server, name)
    agent_dispatch = RoomAgentDispatch(
        agent_name=env_rule.fleet, metadata=Dispatch(org=env_rule.org, env=env_rule.env).dump()
    )
    if existing is None:
        info = SIPDispatchRuleInfo(
            name=name,
            trunk_ids=sorted(set(trunks)),
            numbers=[number],
            rule=SIPDispatchRule(dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=ROOM_PREFIX)),
            room_config=RoomConfiguration(agents=[agent_dispatch]),
        )
        await server.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest(dispatch_rule=info))
        return
    if rules_in(existing, env_rule, trunks, number):
        return
    existing.trunk_ids[:] = sorted({*existing.trunk_ids, *trunks})
    existing.numbers[:] = sorted({*existing.numbers, number})
    existing.room_config.CopyFrom(RoomConfiguration(agents=[agent_dispatch]))
    await server.sip.update_dispatch_rule(existing.sip_dispatch_rule_id, existing)


async def renumber_rule(server: api.LiveKitAPI, rule: SIPDispatchRuleInfo, numbers: list[str]) -> None:
    """Leave the rule these numbers; emptied, it goes."""
    if not numbers:
        await server.sip.delete_dispatch_rule(
            DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule.sip_dispatch_rule_id)
        )
        return
    rule.numbers[:] = numbers
    await server.sip.update_dispatch_rule(rule.sip_dispatch_rule_id, rule)


async def unlist(server: api.LiveKitAPI, org: str, number: str) -> None:
    """Take the number off every trunk of the org on this LiveKit."""
    for trunk in await list_trunks_admitting(server, number):
        if belongs_to(trunk.name, org):
            await renumber_trunk(server, org, trunk, [listed for listed in trunk.numbers if listed != number])


# The rules are listed after the trunks: a trunk emptied takes a rule left with none with it.
async def let_go(server: api.LiveKitAPI, org: str, number: str) -> None:
    """Take the number off the org's trunks and off both of its envs' rules on this LiveKit."""
    await unlist(server, org, number)
    names = {rule_name(org, env) for env in Env}
    for rule in await list_rules(server):
        if rule.name in names and number in rule.numbers:
            await renumber_rule(server, rule, [item for item in rule.numbers if item != number])

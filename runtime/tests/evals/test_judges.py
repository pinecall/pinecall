"""The judges doors: one of Pinecall's switched, one of the org's written, a name nobody wrote refused."""

import json
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.agents.declaration import Tuning
from pinecall_runtime.agents.service import settings
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.auth import Scope
from pinecall_runtime.kit.crypto import Vault
from pinecall_runtime.providers import service as providers
from tests.conftest import Gateway, Tenant, a_finished_call, holding, needs_the_services, received, used_of
from tests.fakes.acme import ACME, MODEL


@needs_the_services
async def test_switching_a_judge_nobody_wrote_is_a_name_typed_wrong(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """A switch names one of Pinecall's or one the org wrote; any other is 404, never a 409 calling it the org's."""
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.put(
            f"/v1/agents/{agent}/judges/nonesuch", json={"on": True}, headers=tenant.person
        )
    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"] == f"{agent} has no judge called nonesuch"


@needs_the_services
async def test_a_refusal_names_the_verb_to_type_never_a_route(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    async with holding(gateway, tenant, agent):
        refused = await gateway.http.delete(f"/v1/agents/{agent}/judges/grounded", headers=tenant.person)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"].endswith("`pinecall judges off grounded` turns it off")


# ── a judge tried is asked as the seal would ask it ──

A_HELD = {"name": "submit_verdict", "arguments": {"reason": "it was", "verdict": "held", "positions": [1]}}


@needs_the_services
async def test_a_judge_tried_on_the_agents_own_judge_model_is_the_orgs_to_pay_and_counts_no_evals(
    sessions: async_sessionmaker[AsyncSession], gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """C B5: `try` read the class and never the agent's settings, so a judge on the org's own key was billed."""
    scope = Scope(tenant.org, Env.sandbox)
    async with sessions.begin() as session:
        await providers.put_own_credentials(session, Vault(os.environ["PINECALL_VAULT_KEY"]), tenant.org, ACME, "key")
        judge = Tuning(judge=f"{ACME}/{MODEL}", judge_options={"replies": [[A_HELD]]})
        await settings.put_tuning(session, scope, agent, judge, settings.Written(author="the suite"))
    async with holding(gateway, tenant, agent):
        call = await a_finished_call(gateway, tenant, agent)
        body = {"name": "polite", "question": "Was the agent polite?", "calls": [call]}
        tried = await gateway.http.post(f"/v1/agents/{agent}/judges/try", json=body, headers=tenant.server)
        assert tried.status_code == 200, tried.text
        assert [row["judgment"]["verdict"] for row in tried.json()["rows"]] == ["held"]
        log = await gateway.http.get(
            f"/v1/agents/{agent}/calls", headers={**tenant.server, "accept": "application/json"}
        )
    spent = [entry["data"] for entry in log.json()["entries"] if entry["type"] == "evals.spent"]
    assert [(one["kind"], one["judge_calls"], one["own_key"]) for one in spent] == [("try", 1, True)]
    assert await used_of(gateway, tenant, "evals") == 0


# ── an agent whose class declares its judges ──


@needs_the_services
async def test_a_class_that_declares_its_judges_is_the_agents_list_and_no_door_writes_it(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    """The list is the class's, each row fixed, its own owned by `class`; a PUT or a DELETE is 409 naming the class."""
    async with holding(gateway, tenant, agent) as app:
        offers = {"name": "offers-next-slot", "question": "Did the agent offer the next free slot?"}
        declared = {"config": {"judges": {"on": ["consent"], "own": [offers]}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": declared}))
        await received(app, "agent.configured")
        rows = (await gateway.http.get(f"/v1/agents/{agent}/judges", headers=tenant.server)).json()["judges"]
        by_name = {row["name"]: row for row in rows}
        assert (by_name["consent"]["on"], by_name["consent"]["fixed"]) == (True, True)
        assert (by_name["grounded"]["on"], by_name["grounded"]["fixed"]) == (False, True)
        assert (by_name["offers-next-slot"]["owner"], by_name["offers-next-slot"]["fixed"]) == ("class", True)
        refused = await gateway.http.put(
            f"/v1/agents/{agent}/judges/consent", json={"on": False}, headers=tenant.server
        )
        assert (refused.status_code, refused.json()["detail"].split(":")[0]) == (
            409,
            f"judges set by the class of {agent}",
        )
        refused = await gateway.http.delete(f"/v1/agents/{agent}/judges/offers-next-slot", headers=tenant.server)
        assert refused.status_code == 409
        # The org's own judges are still the org's to write, and meet the agent's calls on top.
        polite = await gateway.http.put("/v1/org/judges/polite", json={"question": "Polite?"}, headers=tenant.server)
        assert polite.status_code == 200, polite.text
        rows = (await gateway.http.get(f"/v1/agents/{agent}/judges", headers=tenant.server)).json()["judges"]
        assert [row["name"] for row in rows if row["owner"] != "pinecall"] == ["polite", "offers-next-slot"]

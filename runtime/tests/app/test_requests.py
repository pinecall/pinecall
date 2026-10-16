"""A tenant's key reaches the gateway: a request scoped to its org, the app socket, and the box's own key."""

import json

from pinecall_runtime.wire.commands import AgentRegister
from tests.conftest import BOX, Gateway, Tenant, needs_the_services, received


@needs_the_services
async def test_a_tenant_request_runs_scoped_to_its_org(gateway: Gateway, tenant: Tenant) -> None:
    """Every transaction of a tenant's request names its org first (row-level security), and answers."""
    answer = await gateway.http.get("/v1/agents", headers=tenant.server)
    assert answer.status_code == 200, answer.text


@needs_the_services
async def test_the_boxs_own_key_opens_the_operators_endpoints(gateway: Gateway, tenant: Tenant) -> None:
    """PINECALL_OPS_KEY reads what the box admits a new org with; a tenant's key and a wrong one do not."""
    assert (await gateway.http.get("/v1/ops/admission", headers=BOX)).status_code == 200
    # What the billing next to the box reads its feed with, every parameter of the wire flat in the query.
    fed = await gateway.http.get("/v1/ops/usage", params={"after": 0, "limit": 10, "org": "nobody"}, headers=BOX)
    assert fed.status_code == 200, fed.text
    wrong = {"authorization": "Bearer not-the-ops-key"}
    assert (await gateway.http.get("/v1/ops/admission", headers=wrong)).status_code == 401
    assert (await gateway.http.get("/v1/ops/admission", headers=tenant.server)).status_code == 403


# A page's EventSource sets no header: the widget and @pinecall/room read a call's log, and ask a
# code, with the token in the URL beside the query's own names. A query that refused the token
# answered 422 before the token was ever read (2026-10-16, every web chat).
@needs_the_services
async def test_a_page_reads_with_its_token_in_the_url_beside_the_query(gateway: Gateway) -> None:
    """A token in the URL reaches the reading dependency: refused as a token (401), never as a query (422)."""
    not_ours = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ3ZWJfeCJ9.c2lnbmVk"
    asked = {"types": "turn.user", "after": 0, "token": not_ours}
    events = await gateway.http.get("/v1/calls/call_x/events", params=asked)
    code = await gateway.http.get("/v1/codes/123456", params={"wait": 1, "token": not_ours})
    assert (events.status_code, code.status_code) == (401, 401), (events.text, code.text)


@needs_the_services
async def test_the_app_socket_opens_on_a_key(gateway: Gateway, tenant: Tenant) -> None:
    """A websocket's actor is resolved like a request's: the app socket opens on a server key, and registers."""
    async with gateway.socket("/v1/apps", tenant.server) as app:
        register = AgentRegister(routes=[]).model_dump(mode="json")
        await app.send(json.dumps({"type": "agent.register", "agent": "a-socket-test", "call": None, "data": register}))
        assert (await received(app, "agent.registered"))["agent"] == "a-socket-test"

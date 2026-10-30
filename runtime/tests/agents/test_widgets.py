"""The widget's look: the org's row, or the class's when it declares one, which no door writes."""

import json

from tests.conftest import Gateway, Tenant, holding, needs_the_services, received

pytestmark = needs_the_services

LOOK = {"title": "Pip", "tagline": "Brightside Dental", "accent": "#0f766e", "theme": "dark", "autostart": True}


async def test_the_look_the_class_declares_is_what_the_widget_reads_and_a_put_is_refused_naming_the_class(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    door = f"/v1/agents/{agent}/widget"
    async with holding(gateway, tenant, agent) as app:
        before = await gateway.http.put(door, json={"title": "Before"}, headers=tenant.person)
        await app.send(
            json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": {"config": {"widget": LOOK}}})
        )
        await received(app, "agent.configured")
        read = await gateway.http.get(door, headers=tenant.server)
        refused = await gateway.http.put(door, json={"title": "After"}, headers=tenant.person)
    assert before.status_code == 200, before.text
    assert read.json() == {**LOOK, "greeting": None, "fixed": True}
    assert refused.status_code == 409 and refused.json()["detail"].startswith(f"widget set by the class of {agent}")


async def test_an_accent_that_is_no_colour_is_refused_when_declared(
    gateway: Gateway, tenant: Tenant, agent: str
) -> None:
    async with holding(gateway, tenant, agent) as app:
        bad = {"config": {"widget": {"accent": "red; content: url(x)"}}}
        await app.send(json.dumps({"type": "agent.configure", "agent": agent, "call": None, "data": bad}))
        refused = await received(app, "error")
    assert "an accent is a CSS colour" in refused["data"]["message"]

"""The clinic's front desk as Studio holds it: the definition the studio tests build on, and made on a gateway."""

from runtime.enums import Env
from runtime.live.parts import LiveParts
from runtime.studio.service.holder import Holder
from runtime.studio.service.socket import StudioSocket
from runtime.wire.studio import Definition
from tests.conftest import Gateway, Tenant, until


def clinic(**changes: object) -> Definition:
    """The clinic's front desk: one lookup by phone, and the patient's name and reason collected."""
    raw: dict[str, object] = {
        "instructions": "You answer the phone for Clínica Norte. The caller dials from {{call.from}}.",
        "greeting": {"say": "Clínica Norte, buen día."},
        "tools": [
            {
                "name": "findPatient",
                "description": "Finds the patient by phone.",
                "url": "https://agenda.example.com/patients/{phone}",
                "headers": [{"name": "Authorization", "value": "Bearer {{secrets.AGENDA_KEY}}"}],
                "params": [{"name": "phone", "description": "the caller's number"}],
            }
        ],
        "collect": {
            "fields": [
                {"name": "name", "description": "the patient's full name"},
                {"name": "reason", "required": False},
            ],
            "send_to": "https://agenda.example.com/calls",
        },
    }
    raw.update(changes)
    return Definition.model_validate(raw)


def a_tool(**changes: object) -> dict[str, object]:
    """A tool with a header's secret, the way a definition holds one, with these fields changed."""
    return {"name": "a", "description": "x", "url": "https://a.example.com", **changes}


def holder_of(gateway: Gateway) -> Holder:
    """The gateway's own Studio holder."""
    holder: Holder = gateway.state["studio"]
    return holder


def live_of(gateway: Gateway) -> LiveParts:
    """The gateway's live side."""
    live: LiveParts = gateway.state["live"]
    return live


def socket_here(gateway: Gateway, tenant: Tenant) -> StudioSocket:
    """The socket this gateway holds the tenant's sandbox Studio agents on."""
    socket = holder_of(gateway).socket_of(tenant.org, Env.sandbox)
    assert socket is not None
    return socket


async def made(gateway: Gateway, tenant: Tenant, agent: str) -> None:
    """The clinic made in Studio, its secret set, and held by this gateway."""
    await gateway.http.put("/v1/secrets/AGENDA_KEY", json={"value": "the-key"}, headers=tenant.person)
    definition = clinic().model_dump(mode="json", exclude_none=True)
    answered = await gateway.http.post(
        "/v1/studio/agents", json={"name": agent, "definition": definition}, headers=tenant.person
    )
    assert answered.status_code == 200, answered.text
    # Every gateway of a parallel run shares Redis, so the registry says it is held as soon as any of
    # them holds it: this gateway's own Studio socket is what the test's calls and asserts reach.
    holders = live_of(gateway).holders

    def held_here() -> bool:
        socket = holder_of(gateway).socket_of(tenant.org, Env.sandbox)
        return socket is not None and holders.find_on_socket(socket.id, Env.sandbox, agent) is not None

    await until(held_here)

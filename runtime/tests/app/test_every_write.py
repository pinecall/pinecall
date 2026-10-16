"""Every write of a tenant answers a valid key and an empty body with a refusal, never a server error."""

import asyncio
import re
import uuid

import pytest
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from pinecall_runtime.app import create_app
from tests.conftest import Gateway, Tenant, needs_the_services

WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# The box's own writes change what every test of the run shares (its catalog, its admission): they
# are never swept with an empty body. A tenant's writes touch the tenant of the test alone.
THE_BOXS = "/v1/ops"
WITHIN_S = 5.0
# What these writes answer on a test box, and why it is right: each is closed, or opened by
# something other than a tenant's key.
ANSWERED_HERE = {
    ("POST", "/v1/agents/{slug}/personas/generate"): (503, "the suite's catalog names no judge model"),
    ("POST", "/v1/livekit/webhook"): (401, "LiveKit signs its events; a key opens nothing here"),
    ("POST", "/v1/whatsapp/webhook"): (503, "no Meta app on a test box"),
}


def _writes(routes: list[BaseRoute]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            found.extend(_writes(included.routes))
        elif isinstance(route, APIRoute) and not route.path.startswith(THE_BOXS):
            found.extend((method, route.path) for method in sorted((route.methods or set()) & WRITES))
    return sorted(set(found))


ROUTES = _writes(create_app().routes)


def _filled(path: str, tenant: Tenant) -> str:
    values = {
        "named": tenant.slug,
        "org": tenant.slug,
        "call": f"call_{uuid.uuid4().hex}",
        "id": str(uuid.uuid4()),
        "contact": "+15550100000",
        "number": "+15550100000",
        "release": "1",
        "code": "000000",
        "path": "missing.md",
        "file": "missing.md",
    }
    return re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: values.get(m.group(1), "suite-thing"), path)


@needs_the_services
@pytest.mark.timeout(30)
@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_a_write_with_nothing_in_it_is_refused_never_broken(
    method: str, path: str, gateway: Gateway, tenant: Tenant
) -> None:
    """An empty body to a valid key is answered below 500, within its time, and never as unauthenticated."""
    asked = gateway.http.request(method, _filled(path, tenant), json={}, headers=tenant.person)
    try:
        answer = await asyncio.wait_for(asked, WITHIN_S)
    except TimeoutError:
        pytest.fail(f"{method} {path} did not answer within {WITHIN_S} s")
    if (method, path) in ANSWERED_HERE:
        status, why = ANSWERED_HERE[(method, path)]
        assert answer.status_code == status, f"{method} {path} -> {answer.status_code}, expected {status} ({why})"
        return
    assert answer.status_code < 500, f"{method} {path} -> {answer.status_code}: {answer.text[:300]}"
    assert answer.status_code != 401, f"{method} {path} refused a valid key: {answer.text[:300]}"

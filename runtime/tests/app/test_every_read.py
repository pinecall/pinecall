"""Every GET of the API answers a valid key without a server error: the box's on /v1/ops, an admin's elsewhere."""

import asyncio
import re
import uuid

import pytest
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from pinecall_runtime.app import create_app
from tests.conftest import BOX, Gateway, Tenant, needs_the_services

# Live streams answer nothing until something happens: they are opened elsewhere, never swept.
STREAMS = frozenset({"/v1/events", "/v1/ops/events"})
# Closed on a box without the credentials they need, and saying so with 503: a test box has neither.
CLOSED_HERE = {
    "/v1/whatsapp/webhook": "no Meta app",
    "/v1/login/google": "no box-wide sign-in",
    "/v1/login/google/callback": "no box-wide sign-in",
}
# A read that takes longer than this is reported as hanging, which is a failure of its own.
WITHIN_S = 5.0


def _gets(routes: list[BaseRoute]) -> list[str]:
    found: list[str] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            found.extend(_gets(included.routes))
        elif isinstance(route, APIRoute) and "GET" in (route.methods or ()) and route.path not in STREAMS:
            found.append(route.path)
    return sorted(set(found))


READS = _gets(create_app().routes)


# A value of the right shape for each path parameter, naming nothing that exists unless it is the
# tenant's own org: a read of something missing must say 404, never fail.
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
@pytest.mark.parametrize("path", READS)
async def test_a_read_never_fails(path: str, gateway: Gateway, tenant: Tenant) -> None:
    """The read answers below 500, within its time, for a key that is valid where it is asked."""
    headers = BOX if path.startswith("/v1/ops") else tenant.person
    try:
        answer = await asyncio.wait_for(gateway.http.get(_filled(path, tenant), headers=headers), WITHIN_S)
    except TimeoutError:
        pytest.fail(f"GET {path} did not answer within {WITHIN_S} s")
    if path in CLOSED_HERE:
        assert answer.status_code == 503, f"GET {path} -> {answer.status_code}, closed here ({CLOSED_HERE[path]})"
        return
    assert answer.status_code < 500, f"GET {path} -> {answer.status_code}: {answer.text[:300]}"
    assert answer.status_code != 401, f"GET {path} refused a valid key: {answer.text[:300]}"

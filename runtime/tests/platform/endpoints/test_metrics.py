"""`GET /metrics` on a served gateway: every owner's families to the box's loopback, nothing through a proxy."""

from tests.conftest import Gateway, needs_the_services

pytestmark = needs_the_services

FAMILIES = (
    "pinecall_pool_connections",
    "pinecall_loop_running",
    "pinecall_append_seconds",
    "pinecall_held",
    "pinecall_writer_waiting",
    "pinecall_vendor_failing",
    "pinecall_fleet",
)


async def test_the_gateway_says_every_owners_families_to_its_own_loopback(gateway: Gateway) -> None:
    answer = await gateway.http.get("/metrics")
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("text/plain; version=0.0.4")
    for name in FAMILIES:
        assert f"# TYPE {name} " in answer.text, name
    assert "pinecall_loop_running{" in answer.text


async def test_a_request_a_proxy_passed_on_is_refused(gateway: Gateway) -> None:
    answer = await gateway.http.get("/metrics", headers={"x-forwarded-for": "127.0.0.1"})
    assert answer.status_code == 403
    assert "never a forwarded request" in answer.json()["detail"]

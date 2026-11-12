"""The gateway comes up on the test database and answers: the lifespan wires everything, once."""

from tests.conftest import Gateway, needs_the_services


@needs_the_services
async def test_the_box_says_who_it_is(gateway: Gateway) -> None:
    """`/.well-known/pinecall` answers before anybody holds a key."""
    answer = await gateway.http.get("/.well-known/pinecall")
    assert answer.status_code == 200, answer.text
    assert "version" in answer.json()


@needs_the_services
async def test_a_key_is_asked_for(gateway: Gateway) -> None:
    """An endpoint of a key refuses a bare request with 401 and the Bearer challenge."""
    answer = await gateway.http.get("/v1/ops/orgs")
    assert answer.status_code == 401
    assert answer.headers["www-authenticate"] == "Bearer"
    assert "detail" in answer.json()


@needs_the_services
async def test_the_console_is_the_last_route(gateway: Gateway) -> None:
    """A path nothing answers is the console's; this checkout has none built, and says so."""
    answer = await gateway.http.get("/anything/at/all")
    assert answer.status_code == 404
    assert "not built" in answer.json()["detail"]


@needs_the_services
async def test_the_api_documents_itself(gateway: Gateway) -> None:
    """Every endpoint is in the OpenAPI document, under /v1."""
    answer = await gateway.http.get("/openapi.json")
    assert answer.status_code == 200
    paths = answer.json()["paths"]
    assert "/v1/calls" in paths
    assert len(paths) > 200

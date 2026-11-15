"""An app connected as a person: registered, approved in a browser, its code exchanged once for a key, revoked."""

import secrets
from urllib.parse import parse_qs, urlsplit

import httpx

from runtime.signin.service.connections import challenge_of
from tests.conftest import Gateway, Tenant, needs_the_services

THE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
FORM = {"content-type": "application/x-www-form-urlencoded"}


async def registered(gateway: Gateway, name: str = "Claude", callback: str = THE_CALLBACK) -> str:
    """An app registered as its own software does it, saying more of itself than the gateway keeps."""
    said = {
        "client_name": name,
        "redirect_uris": [callback],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "logo_uri": "https://app.example/logo.png",
    }
    answer = await gateway.http.post("/v1/oauth/register", json=said)
    assert answer.status_code == 201, answer.text
    assert answer.json()["token_endpoint_auth_method"] == "none"
    return str(answer.json()["client_id"])


async def approved(gateway: Gateway, tenant: Tenant, client_id: str, verifier: str, state: str | None = "st-1") -> str:
    """The address the person's browser is sent to once they approve, the app's code in it."""
    asking = {"client_id": client_id, "redirect_uri": THE_CALLBACK, "code_challenge": challenge_of(verifier)}
    answer = await gateway.http.post("/v1/oauth/authorization", json={**asking, "state": state}, headers=tenant.person)
    assert answer.status_code == 200, answer.text
    assert answer.json()["org"] == tenant.org
    return str(answer.json()["redirect"])


async def exchanged(gateway: Gateway, **form: str) -> httpx.Response:
    """What the token endpoint answers the form an app posts."""
    return await gateway.http.post("/v1/oauth/token", data={"grant_type": "authorization_code", **form}, headers=FORM)


@needs_the_services
async def test_the_gateway_says_what_it_is_to_an_app_before_anything(gateway: Gateway) -> None:
    """RFC 8414's document: where to ask, exchange, register and revoke, S256 alone, read by any page."""
    answer = await gateway.http.get("/.well-known/oauth-authorization-server")
    said = answer.json()
    assert answer.status_code == 200 and answer.headers["access-control-allow-origin"] == "*"
    assert said["issuer"] == gateway.url
    assert said["authorization_endpoint"] == f"{gateway.url}/connect"
    assert said["token_endpoint"] == f"{gateway.url}/v1/oauth/token"
    assert said["registration_endpoint"] == f"{gateway.url}/v1/oauth/register"
    assert said["revocation_endpoint"] == f"{gateway.url}/v1/oauth/revoke"
    assert said["code_challenge_methods_supported"] == ["S256"]
    assert said["token_endpoint_auth_methods_supported"] == ["none"]
    assert said["client_id_metadata_document_supported"] is True


@needs_the_services
async def test_an_app_approved_in_a_browser_exchanges_its_code_for_the_persons_key_once(
    gateway: Gateway, tenant: Tenant
) -> None:
    """Registered, read by the person, approved, sent back with a code, and the code exchanged for a key of theirs."""
    client_id, verifier = await registered(gateway), secrets.token_urlsafe(48)
    asking = {"client_id": client_id, "redirect_uri": THE_CALLBACK, "code_challenge": challenge_of(verifier)}
    read = await gateway.http.get("/v1/oauth/authorization", params=asking, headers=tenant.person)
    assert read.json() == {"client_name": "Claude", "redirect_host": "claude.ai"}
    assert (await gateway.http.get("/v1/oauth/authorization", params=asking)).status_code == 401

    back = urlsplit(await approved(gateway, tenant, client_id, verifier))
    carried = {name: values[0] for name, values in parse_qs(back.query).items()}
    assert f"{back.scheme}://{back.netloc}{back.path}" == THE_CALLBACK
    assert (carried["state"], carried["iss"]) == ("st-1", gateway.url)

    form = {"code": carried["code"], "code_verifier": verifier, "client_id": client_id, "redirect_uri": THE_CALLBACK}
    answer = await exchanged(gateway, **form)
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    assert (answer.json()["token_type"], answer.json()["scope"]) == ("Bearer", "pinecall")
    who = await gateway.http.get("/v1/whoami", headers={"authorization": f"Bearer {answer.json()['access_token']}"})
    assert (who.json()["org"], who.json()["label"], who.json()["subject"]) == (tenant.org, "Claude", tenant.member)

    again = await exchanged(gateway, **form)
    assert (again.status_code, again.json()["error"]) == (400, "invalid_grant")
    assert again.json()["error_description"] == again.json()["detail"]


@needs_the_services
async def test_a_code_is_exchanged_only_by_the_app_it_was_given_to_with_its_own_verifier(
    gateway: Gateway, tenant: Tenant
) -> None:
    """Another verifier, another app, another address: each refused as OAuth names it, and the code still its app's."""
    client_id, verifier = await registered(gateway), secrets.token_urlsafe(48)
    back = await approved(gateway, tenant, client_id, verifier, state=None)
    carried = parse_qs(urlsplit(back).query)
    assert "state" not in carried
    code = carried["code"][0]
    another = await registered(gateway, "Another app")
    for wrong in (
        {"code": code, "code_verifier": secrets.token_urlsafe(48), "client_id": client_id},
        {"code": code, "code_verifier": verifier, "client_id": another},
        {"code": code, "code_verifier": verifier, "client_id": client_id, "redirect_uri": "https://claude.ai/other"},
        {"code": "pca_made-up", "code_verifier": verifier, "client_id": client_id},
    ):
        refused = await exchanged(gateway, **wrong)
        assert (refused.status_code, refused.json()["error"]) == (400, "invalid_grant"), refused.text
    assert (await exchanged(gateway, code=code, client_id=client_id)).json()["error"] == "invalid_request"
    other_grant = await gateway.http.post("/v1/oauth/token", data={"grant_type": "client_credentials"}, headers=FORM)
    assert other_grant.json()["error"] == "unsupported_grant_type"
    assert (await exchanged(gateway, code=code, code_verifier=verifier, client_id=client_id)).status_code == 200


@needs_the_services
async def test_an_approval_is_never_sent_where_the_app_did_not_register(gateway: Gateway, tenant: Tenant) -> None:
    """An address the app never registered, an app nobody registered, a challenge that is not S256: nothing minted."""
    client_id, challenge = await registered(gateway), challenge_of(secrets.token_urlsafe(48))
    for wrong, error in (
        ({"client_id": client_id, "redirect_uri": "https://evil.example/cb"}, "invalid_redirect_uri"),
        ({"client_id": "pcc_made-up", "redirect_uri": THE_CALLBACK}, "invalid_client"),
        ({"client_id": client_id, "redirect_uri": THE_CALLBACK, "code_challenge_method": "plain"}, "invalid_request"),
    ):
        body = {"code_challenge": challenge, **wrong}
        refused = await gateway.http.post("/v1/oauth/authorization", json=body, headers=tenant.person)
        assert (refused.status_code, refused.json()["error"]) == (400, error), refused.text
    with_a_server = {"client_id": client_id, "redirect_uri": THE_CALLBACK, "code_challenge": challenge}
    server = await gateway.http.post("/v1/oauth/authorization", json=with_a_server, headers=tenant.server)
    assert server.status_code == 403


@needs_the_services
async def test_an_app_stops_its_own_key_and_a_made_up_token_stops_nothing(gateway: Gateway, tenant: Tenant) -> None:
    """RFC 7009: the key an app revokes opens nothing after; a made-up token is answered 200 all the same."""
    client_id, verifier = await registered(gateway), secrets.token_urlsafe(48)
    code = parse_qs(urlsplit(await approved(gateway, tenant, client_id, verifier)).query)["code"][0]
    key = (await exchanged(gateway, code=code, code_verifier=verifier, client_id=client_id)).json()["access_token"]
    bearer = {"authorization": f"Bearer {key}"}
    assert (await gateway.http.get("/v1/whoami", headers=bearer)).status_code == 200
    assert (await gateway.http.post("/v1/oauth/revoke", data={"token": "made-up"}, headers=FORM)).status_code == 200
    assert (await gateway.http.get("/v1/whoami", headers=bearer)).status_code == 200
    assert (await gateway.http.post("/v1/oauth/revoke", data={"token": key}, headers=FORM)).status_code == 200
    assert (await gateway.http.get("/v1/whoami", headers=bearer)).status_code == 401
    assert (await gateway.http.get("/v1/whoami", headers=tenant.person)).status_code == 200


@needs_the_services
async def test_an_app_in_a_page_of_its_own_registers_and_exchanges_from_there(gateway: Gateway) -> None:
    """A browser is given leave to post the three forms from any origin, with no credentials."""
    asked = {"origin": "https://inspector.example", "access-control-request-method": "POST"}
    preflight = await gateway.http.options(
        "/v1/oauth/register", headers={**asked, "access-control-request-headers": "content-type"}
    )
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == "*"
    refused = await gateway.http.post(
        "/v1/oauth/token", data={"grant_type": "authorization_code"}, headers={**FORM, "origin": asked["origin"]}
    )
    assert refused.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in refused.headers

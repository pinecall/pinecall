"""An app connected as a person (OAuth 2.1): what the gateway is to it, its registration, the approval, the exchange."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from runtime.accounts.auth import PersonKey, PublicUrl, TheKeyCache
from runtime.postgres import Session, TheBoxSession
from runtime.signin import schemas
from runtime.signin.auth import TheClients, TheConnections, TheForm
from runtime.signin.service import connections
from runtime.signin.service.connections import Asking

router = APIRouter()

# Read by an app in any page, before it holds anything: no key, no cookie, nothing of anybody's.
ANY_PAGE = {"Access-Control-Allow-Origin": "*"}
# A key is answered once and kept by nobody on the way (RFC 6749 section 5.1).
NEVER_KEPT = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server(base: PublicUrl, response: Response) -> schemas.AuthorizationServer:
    """Where an app asks to act as a person, exchanges its code, registers and revokes."""
    response.headers.update(ANY_PAGE)
    return schemas.AuthorizationServer.at(base, connections.SCOPE)


@router.post(schemas.OAUTH_REGISTER, status_code=201)
async def register_client(body: schemas.RegisterClient, clients: TheClients) -> schemas.ClientRegistered:
    """An app's id, made of what it calls itself and where it may be sent back; nothing is kept."""
    client = clients.register(body.client_name, body.redirect_uris)
    return schemas.ClientRegistered(client_id=client.id, client_name=client.name, redirect_uris=[*client.redirect_uris])


@router.get("/v1/oauth/authorization")
async def read_connection(
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    code_challenge: Annotated[str, Query()],
    _actor: PersonKey,
    clients: TheClients,
    code_challenge_method: Annotated[str, Query()] = connections.THE_CHALLENGE_METHOD,
) -> schemas.ConnectionAsked:
    """Who asks to act as the person this browser is, and where their approval would be sent."""
    asking = Asking(client_id, redirect_uri, code_challenge, code_challenge_method)
    return schemas.ConnectionAsked.of(await connections.read_asking(clients, asking))


@router.post("/v1/oauth/authorization")
async def approve_connection(
    body: schemas.ApproveConnection,
    actor: PersonKey,
    base: PublicUrl,
    clients: TheClients,
    approvals: TheConnections,
    session: Session,
) -> schemas.ConnectionApproved:
    """Let the app act as the person this browser is; the address to send it back to, with its code."""
    asking = Asking(body.client_id, body.redirect_uri, body.code_challenge, body.code_challenge_method, body.state)
    approved = await connections.approve(session, approvals, clients, asking, actor, issuer=base, org=body.org)
    return schemas.ConnectionApproved.of(approved)


@router.post(schemas.OAUTH_TOKEN)
async def exchange_code(form: TheForm, approvals: TheConnections, response: Response) -> schemas.TokenIssued:
    """The key an approval minted, for the code and the verifier of its challenge; once."""
    response.headers.update(NEVER_KEPT)
    key = await connections.exchange_form(approvals, form)
    return schemas.TokenIssued(access_token=key, scope=connections.SCOPE)


@router.post(schemas.OAUTH_REVOKE)
async def revoke_token(form: TheForm, cache: TheKeyCache, session: TheBoxSession) -> schemas.Empty:
    """Stop the key an app holds, at the app's own word; 200 whatever the token was."""
    await connections.disconnect(session, cache, form.get("token", ""))
    return schemas.Empty()

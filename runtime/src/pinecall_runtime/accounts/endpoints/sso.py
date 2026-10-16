"""The org's identity provider: signing in through it, and the org setting it up and verifying its domains."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    Client,
    PublicUrl,
    SignInsDep,
    TeamKey,
)
from pinecall_runtime.accounts.service import keys, orgs, signin, sso
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
    PinecallError,
    UpstreamError,
    ValidationError,
)
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.postgres import Session

router = APIRouter()

THE_CONSOLE = "/"
THE_CARD = "/cli"
CLIENT_HEADER = "x-pinecall-client"
FOUND = 302


@router.get("/v1/login/sso")
async def start_sso(
    org: Annotated[str, Query()],
    request: Request,
    client: Client,
    base: PublicUrl,
    session: Session,
    sign_ins_: SignInsDep,
    pairing: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """302 to the org's provider, with a state, a nonce and a PKCE challenge."""
    owner = await orgs.find_org(session, org)
    provider = None if owner is None else await sso.get_provider(session, handles_of(request).vault, owner.id)
    if owner is None or provider is None:
        raise sso.NoProvider(org)
    await sign_ins_.attempts.check(f"{client} sso/{owner.slug}", "sign-ins from here")
    endpoints = await sso.discover(handles_of(request).http, provider.issuer)
    begun = await sso.begin_handshake(sign_ins_.handshakes, f"{base}{sso.CALLBACK}", org=owner.id, pairing=pairing)
    return RedirectResponse(sso.authorization_url(endpoints, provider, begun), FOUND)


@router.get("/v1/login/sso/callback")
async def finish_sso(
    state: str,
    request: Request,
    session: Session,
    sign_ins_: SignInsDep,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The code exchanged, the person seated, and 302 to the console with a login code."""
    begun = await sign_ins_.handshakes.spend(state)
    if begun is None:
        raise ValidationError("no sign-in answers to that: it was finished already, it expired, or it never started")
    if error is not None:
        return _refused(f"the sign-in was refused at the provider: {error}")
    if not code:
        return _refused("the provider sent no authorization code back")
    try:
        member = await sso.seat_from_callback(session, handles_of(request).vault, handles_of(request).http, begun, code)
    except PinecallError as refusal:
        return _refused(str(refusal))
    login, _ = await sign_ins_.codes.mint(signin.holder_of_member(member))
    if begun.pairing is None:
        return RedirectResponse(f"{THE_CONSOLE}?{httpx.QueryParams({'login': login})}", FOUND)
    return RedirectResponse(f"{THE_CARD}?{httpx.QueryParams({'c': begun.pairing, 'login': login})}", FOUND)


@router.post("/v1/login/sso/discover")
async def discover_sso(
    body: schemas.DiscoverSso, request: Request, client: Client, session: Session, sign_ins_: SignInsDep
) -> schemas.SsoOrgList:
    """The orgs whose provider signs in this address's domain, oldest first."""
    email = body.email.strip().lower()
    await sign_ins_.attempts.check(f"{client} sso/{email}", email)
    domain = email.rpartition("@")[2]
    if not sso.A_DOMAIN.match(domain):
        return schemas.SsoOrgList(orgs=[])
    rows: list[schemas.SsoOrgRow] = []
    for provider in await sso.providers_for_domain(session, handles_of(request).vault, domain):
        org = await orgs.find_org(session, provider.org)
        if org is not None:
            rows.append(schemas.SsoOrgRow(org=org.id, slug=org.slug, name=org.name))
    return schemas.SsoOrgList(orgs=rows)


@router.get("/v1/org/sso")
async def get_sso(actor: TeamKey, request: Request, base: PublicUrl, session: Session) -> schemas.SsoRow:
    """The org's provider, never its secret, and the redirect URI to register there."""
    provider = await sso.get_provider(session, handles_of(request).vault, actor.org)
    return sso.sso_row(provider, base, await sso.proofs_of(session, actor.org))


@router.put("/v1/org/sso")
async def put_sso(
    body: schemas.PutSso, actor: TeamKey, request: Request, base: PublicUrl, session: Session
) -> schemas.SsoRow:
    """Replace the org's provider whole, once its issuer answered as one."""
    keys.check_may_grant(actor, body.role, production=False)
    provider = sso.Provider(
        org=actor.org,
        issuer=body.issuer.strip(),
        client_id=body.client_id.strip(),
        client_secret=body.client_secret,
        domains=tuple(d.strip().lower().removeprefix("@") for d in body.domains),
        role=body.role,
        required=body.required,
    )
    try:
        await sso.discover(handles_of(request).http, provider.issuer)
    except UpstreamError as unanswered:
        raise ValidationError(f"{unanswered}: nothing was kept") from unanswered
    if provider.required and not await sso.verified_domains(session, actor.org) & frozenset(provider.domains):
        raise Conflict(
            "no domain of this SSO is verified yet: publish each domain's TXT record and verify it, then require it"
        )
    proofs = await sso.put_provider(session, handles_of(request).vault, provider)
    return sso.sso_row(provider, base, proofs)


@router.post("/v1/org/sso/domains/{domain}/verify")
async def verify_sso_domain(domain: str, actor: TeamKey, session: Session) -> schemas.SsoDomainProofRow:
    """Look for the domain's TXT record and, found, offer the provider for the domain."""
    proof = await sso.verify_domain(session, actor.org, domain.strip().lower().removeprefix("@"))
    return sso.proof_row(proof)


@router.delete("/v1/org/sso", status_code=204)
async def drop_sso(actor: TeamKey, session: Session) -> None:
    """Forget the org's provider: passwords open it again."""
    if not await sso.delete_provider(session, actor.org):
        raise NotFound("this org signs in with no identity provider")


def _refused(sentence: str) -> RedirectResponse:
    return RedirectResponse(f"{THE_CONSOLE}?{httpx.QueryParams({'refused': sentence})}", FOUND)

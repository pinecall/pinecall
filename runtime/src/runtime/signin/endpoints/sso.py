"""The org's identity provider: signing in through it, the org setting it up, and the operator's break-glass."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from runtime.accounts.auth import PublicUrl, TeamKey, TheKeyCache, TheNamedOrg
from runtime.handles import TheVault
from runtime.postgres import Session, TheBoxSession
from runtime.signin import schemas
from runtime.signin.auth import Client, TheLoginCodes, TheOidc, TheSignInAttempts
from runtime.signin.service import sso
from runtime.signin.service.oidc import Answer

router = APIRouter()

FOUND = 302


@router.get("/v1/login/sso")
async def start_sso(
    org: Annotated[str, Query()],
    client: Client,
    base: PublicUrl,
    vault: TheVault,
    oidc: TheOidc,
    attempts: TheSignInAttempts,
    session: Session,
    pairing: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """302 to the org's provider, with a state, a nonce and a PKCE challenge."""
    callback = f"{base}{schemas.SSO_CALLBACK}"
    url = await sso.begin(session, vault, oidc, attempts, org, client=client, redirect_uri=callback, pairing=pairing)
    return RedirectResponse(url, FOUND)


@router.get(schemas.SSO_CALLBACK)
async def finish_sso(
    state: str,
    cache: TheKeyCache,
    vault: TheVault,
    oidc: TheOidc,
    login_codes: TheLoginCodes,
    session: Session,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The code exchanged, the person seated, and 302 to the console with a login code, or with why not."""
    landing = await sso.finish(session, cache, vault, oidc, login_codes, Answer(state, code, error))
    return RedirectResponse(schemas.Landed.of(landing).location, FOUND)


@router.post("/v1/login/sso/discover")
async def discover_sso(
    body: schemas.DiscoverSso, client: Client, attempts: TheSignInAttempts, session: Session
) -> schemas.SsoOrgList:
    """The orgs whose provider signs in this address's domain, oldest first."""
    found = await sso.list_orgs_for_address(session, attempts, body.email, client=client)
    return schemas.SsoOrgList(orgs=[schemas.SsoOrgRow(org=org.id, slug=org.slug, name=org.name) for org in found])


# ── the org's own ──


@router.get("/v1/org/sso")
async def get_sso(actor: TeamKey, base: PublicUrl, vault: TheVault, session: Session) -> schemas.SsoRow:
    """The org's provider, never its secret, and the redirect URI to register there."""
    wiring = await sso.wiring_of(session, vault, actor.org, redirect_uri=f"{base}{schemas.SSO_CALLBACK}")
    return schemas.SsoRow.of(wiring)


@router.put("/v1/org/sso")
async def put_sso(
    body: schemas.PutSso, actor: TeamKey, base: PublicUrl, vault: TheVault, oidc: TheOidc, session: Session
) -> schemas.SsoRow:
    """Replace the org's provider whole, once its issuer answered as one."""
    wanted = sso.Wanted(body.issuer, body.client_id, body.client_secret, body.domains, body.role, body.required)
    callback = f"{base}{schemas.SSO_CALLBACK}"
    wiring = await sso.put_provider_as_admin(session, vault, oidc, actor, wanted, redirect_uri=callback)
    return schemas.SsoRow.of(wiring)


@router.post("/v1/org/sso/domains/{domain}/verify")
async def verify_sso_domain(domain: str, actor: TeamKey, session: Session) -> schemas.SsoDomainProofRow:
    """Look for the domain's TXT record and, found, offer the provider for the domain."""
    return schemas.SsoDomainProofRow.of(await sso.verify_domain(session, actor.org, domain))


@router.delete("/v1/org/sso", status_code=204)
async def delete_sso(actor: TeamKey, session: Session) -> None:
    """Forget the org's provider: passwords open it again."""
    await sso.delete_provider(session, actor.org)


# ── the operator's ──


@router.get("/v1/ops/orgs/{named}/sso")
async def org_sso(org: TheNamedOrg, base: PublicUrl, vault: TheVault, session: TheBoxSession) -> schemas.SsoRow:
    """Which provider the org signs in with, never its secret."""
    wiring = await sso.wiring_of(session, vault, org.id, redirect_uri=f"{base}{schemas.SSO_CALLBACK}")
    return schemas.SsoRow.of(wiring)


# The break-glass: a password opens the org again while its provider is down. Never the other way:
# requiring the provider is the org's own call.
@router.put("/v1/ops/orgs/{named}/sso/required")
async def require_sso(
    org: TheNamedOrg, body: schemas.SsoRequired, base: PublicUrl, vault: TheVault, session: TheBoxSession
) -> schemas.SsoRow:
    """Whether a password may still open the org beside its provider."""
    callback = f"{base}{schemas.SSO_CALLBACK}"
    wiring = await sso.set_required(session, vault, org, required=body.required, redirect_uri=callback)
    return schemas.SsoRow.of(wiring)

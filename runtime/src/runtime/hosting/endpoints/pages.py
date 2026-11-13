"""An app's page, served at the app's own name: what it needs, a visitor's ticket, code and dictation, and its files."""

from fastapi import APIRouter, Response

from runtime.fleet.auth import TheRoster
from runtime.handles import TheSettings, TheVault
from runtime.hosting import schemas
from runtime.hosting.auth import ThePage, ThePages, ThePageTickets
from runtime.hosting.service import pages
from runtime.live import schemas as live_schemas
from runtime.live import service as live
from runtime.live.auth import TheCodes, TheLive, TheSigner
from runtime.postgres import Session
from runtime.providers import service as providers
from runtime.providers.auth import TheTokenKey
from runtime.signin.auth import Client, TheTurnstile

router = APIRouter()

# Served at the app's own name, never at the gateway's: the middleware that names a request's host
# in its path sends it here, and `ThePage` answers only the name it came in by.
PAGE_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}
# The page itself is read again on every visit; a built asset is kept a while.
THE_PAGE = {**PAGE_HEADERS, "Cache-Control": "no-store"}
AN_ASSET = {**PAGE_HEADERS, "Cache-Control": "public, max-age=300"}


@router.get("/v1/pages/{host}/pinecall/config")
async def page_config(paged: ThePage, settings: TheSettings) -> schemas.PageConfig:
    """What an app's page needs before it asks for a ticket: its agent, and the captcha's site key."""
    return schemas.PageConfig(agent=paged.page.agent, turnstile=settings.turnstile_site_key)


@router.post("/v1/pages/{host}/pinecall/token", status_code=201)
async def page_ticket(
    host: str,
    body: schemas.PageTicketRequest,
    paged: ThePage,
    client: Client,
    tickets: ThePageTickets,
    turnstile: TheTurnstile,
    parts: TheLive,
    signer: TheSigner,
    roster: TheRoster,
    session: Session,
) -> live_schemas.MintTokenResponse:
    """A seat in a new call with the page's agent, for a visitor who passed the captcha."""
    await pages.admit_visitor(tickets, turnstile, host, body.turnstile, client)
    wanted = live.Mint(agent=paged.page.agent, scope=body.scope, resume=body.resume)
    minted = await live.mint_room_token(session, parts, signer, roster, pages.visitor_of(paged), wanted)
    return live_schemas.MintTokenResponse.of(minted)


@router.post("/v1/pages/{host}/pinecall/code", status_code=201)
async def page_code(
    host: str,
    body: schemas.PageCodeRequest,
    paged: ThePage,
    client: Client,
    tickets: ThePageTickets,
    turnstile: TheTurnstile,
    codes: TheCodes,
    signer: TheSigner,
    session: Session,
) -> live_schemas.IssueCodeResponse:
    """A code a visitor keys when they call the page's agent, so the page follows that call."""
    await pages.admit_visitor(tickets, turnstile, host, body.turnstile, client)
    asked = live_schemas.IssueCodeRequest(agent=paged.page.agent)
    issued = await live.issue_code(session, codes, signer, pages.visitor_of(paged), asked.agent, asked.ttl_s, asked.log)
    return live_schemas.IssueCodeResponse.of(issued)


# A visitor dictates into the page's field: the microphone goes from their browser to the gateway's
# socket, and the page never holds a key. Asked as a ticket is, past the captcha and so many a
# minute from one address, since each one spends the org's transcription.
@router.post("/v1/pages/{host}/pinecall/dictation")
async def page_dictation(
    host: str,
    body: schemas.PageDictationRequest,
    paged: ThePage,
    client: Client,
    tickets: ThePageTickets,
    turnstile: TheTurnstile,
    settings: TheSettings,
    own_key: TheTokenKey,
    vault: TheVault,
    session: Session,
) -> schemas.PageDictation:
    """One dictation's socket, a minute long, for a visitor who passed the captcha."""
    await pages.admit_visitor(tickets, turnstile, host, body.turnstile, client)
    scope = pages.visitor_of(paged).scope
    minted = await providers.mint_for_a_page(session, vault, scope, body.language, own_key)
    return schemas.PageDictation(url=settings.base_url.replace("http", "ws", 1) + minted.path)


@router.get("/v1/pages/{host}/files/{path:path}")
async def page_file(path: str, paged: ThePage, kept: ThePages, session: Session) -> Response:
    """One file of an app's page, from the release that runs; a path that names no file is the page itself."""
    found = await kept.file_of(session, paged, path)
    return Response(found.body, media_type=found.media_type, headers=THE_PAGE if found.is_the_page else AN_ASSET)

"""Continue with Google: off to Google, and back — signed in, sent to name a workspace, or told why not."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from pinecall_runtime.accounts.auth import Client, PublicUrl, SignInsDep
from pinecall_runtime.accounts.endpoints.sso import FOUND, refused_on_the_console, signed_in_on_the_console
from pinecall_runtime.accounts.service import google, signin, sso
from pinecall_runtime.exceptions import PinecallError, ValidationError
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.postgres import Session

router = APIRouter()

# Where somebody Google vouched for and nobody knows names their workspace.
THE_SIGNUP = "/signup"
# What Google says when the person closed its page or said no.
CANCELLED = "access_denied"


@router.get("/v1/login/google")
async def start_google(
    request: Request,
    client: Client,
    base: PublicUrl,
    session: Session,
    sign_ins_: SignInsDep,
    pairing: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """302 to Google, with a state, a nonce and a PKCE challenge."""
    handles = handles_of(request)
    at_google = await google.get_client(session, handles.vault)
    if at_google is None:
        raise google.NoGoogle()
    await sign_ins_.attempts.check(f"{client} google", "sign-ins from here")
    endpoints = await sso.discover(handles.http, google.ISSUER)
    begun = await sso.begin_handshake(sign_ins_.handshakes, f"{base}{google.CALLBACK}", org=None, pairing=pairing)
    return RedirectResponse(sso.authorization_url(endpoints, at_google, begun, prompt=google.PROMPT), FOUND)


@router.get(google.CALLBACK)
async def finish_google(
    state: str,
    request: Request,
    session: Session,
    sign_ins_: SignInsDep,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The code exchanged; 302 to the console signed in, to the sign-up for a newcomer, or with why not."""
    begun = await sign_ins_.handshakes.spend(state)
    # An org's own provider began with its org named, and finishes at its own callback.
    if begun is None or begun.org is not None:
        raise ValidationError("no sign-in answers to that: it was finished already, it expired, or it never started")
    if error == CANCELLED:
        return refused_on_the_console("the sign-in with Google was not finished")
    if error is not None:
        return refused_on_the_console(f"Google refused the sign-in: {error}")
    if not code:
        return refused_on_the_console("Google sent no authorization code back")
    handles = handles_of(request)
    try:
        at_google = await google.get_client(session, handles.vault)
        if at_google is None:
            raise google.NoGoogle()
        vouched = await google.vouched_for(handles.http, at_google, begun, code)
        member = await google.member_for(session, vouched.email)
    except PinecallError as refusal:
        return refused_on_the_console(str(refusal))
    if member is not None:
        login, _ = await sign_ins_.codes.mint(signin.holder_of_member(member))
        return signed_in_on_the_console(login, begun.pairing)
    if not handles.settings.signup:
        return refused_on_the_console(
            f"nobody here answers to {vouched.email}, and this platform takes no sign-ups: "
            "ask an admin of your workspace to invite you"
        )
    token = sign_ins_.newcomers.new_secret()
    await sign_ins_.newcomers.keep(token, signin.Newcomer(vouched.email, vouched.person, begun.pairing))
    asked = {"google": token} if begun.pairing is None else {"google": token, "c": begun.pairing}
    return RedirectResponse(f"{THE_SIGNUP}?{httpx.QueryParams(asked)}", FOUND)

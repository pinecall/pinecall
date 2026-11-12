"""Sign-in's dependencies: the getters of what sign-in keeps between two requests, and where a request came from."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from runtime.platform import service as platform
from runtime.signin.service.codes import LoginCodes
from runtime.signin.service.google import Newcomers
from runtime.signin.service.oidc import Oidc
from runtime.signin.service.pairings import Pairings
from runtime.signin.service.passwords import PasswordThrottle
from runtime.signin.service.signup import SignUps
from runtime.signin.service.turnstile import Turnstile


def login_codes_of(connection: HTTPConnection) -> LoginCodes:
    """The codes a browser signs in with."""
    codes: LoginCodes = connection.state.login_codes
    return codes


def pairings_of(connection: HTTPConnection) -> Pairings:
    """The terminals waiting to be signed in."""
    pairings: Pairings = connection.state.pairings
    return pairings


def sign_ups_of(connection: HTTPConnection) -> SignUps:
    """The sign-ups waiting for their code."""
    sign_ups: SignUps = connection.state.sign_ups
    return sign_ups


def newcomers_of(connection: HTTPConnection) -> Newcomers:
    """The people Google vouched for whom nobody here knows yet."""
    newcomers: Newcomers = connection.state.newcomers
    return newcomers


def oidc_of(connection: HTTPConnection) -> Oidc:
    """The gateway as an OpenID Connect client."""
    oidc: Oidc = connection.state.oidc
    return oidc


def password_throttle_of(connection: HTTPConnection) -> PasswordThrottle:
    """The tries a password is held to."""
    throttle: PasswordThrottle = connection.state.password_throttle
    return throttle


def sign_in_attempts_of(connection: HTTPConnection) -> platform.AttemptThrottle:
    """The tries every other way in is held to, by the name each counts under."""
    attempts: platform.AttemptThrottle = connection.state.sign_in_attempts
    return attempts


def turnstile_of(connection: HTTPConnection) -> Turnstile:
    """The box's Turnstile: Cloudflare's verifier where the operator set a secret, else one that passes all."""
    turnstile: Turnstile = connection.state.turnstile
    return turnstile


def client_of(request: Request) -> str:
    """The address a request came from, as the throttle counts it."""
    return request.client.host if request.client is not None else "unknown"


TheLoginCodes = Annotated[LoginCodes, Depends(login_codes_of)]
ThePairings = Annotated[Pairings, Depends(pairings_of)]
TheSignUps = Annotated[SignUps, Depends(sign_ups_of)]
TheNewcomers = Annotated[Newcomers, Depends(newcomers_of)]
TheOidc = Annotated[Oidc, Depends(oidc_of)]
ThePasswordThrottle = Annotated[PasswordThrottle, Depends(password_throttle_of)]
TheSignInAttempts = Annotated[platform.AttemptThrottle, Depends(sign_in_attempts_of)]
TheTurnstile = Annotated[Turnstile, Depends(turnstile_of)]
Client = Annotated[str, Depends(client_of)]

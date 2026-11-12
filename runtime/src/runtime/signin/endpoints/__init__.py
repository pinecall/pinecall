"""The sign-in router: the gateway's own page, logins, pairings, sign-ups, an org's provider, Google."""

from fastapi import APIRouter

from runtime.signin.endpoints import gateway, google, pairings, signin, signup, sso

router = APIRouter()
for family in (gateway, signin, pairings, signup, sso, google):
    router.include_router(family.router)

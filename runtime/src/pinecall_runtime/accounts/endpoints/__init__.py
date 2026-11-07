"""The accounts router: identity, sign-in, Google, pairings, invitations, members, keys, sign-up, SSO, mail, ops."""

from fastapi import APIRouter

from pinecall_runtime.accounts.endpoints import (
    box,
    google,
    identity,
    invitations,
    keys,
    mail,
    members,
    ops,
    pairings,
    signin,
    signup,
    sso,
)

router = APIRouter()
for family in (identity, signin, google, pairings, invitations, members, keys, signup, sso, mail, ops, box):
    router.include_router(family.router)

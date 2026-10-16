"""The accounts router: identity, sign-in, pairings, invitations, members, keys, sign-up, SSO, mail, the operator's."""

from fastapi import APIRouter

from pinecall_runtime.accounts.endpoints import (
    box,
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
for family in (identity, signin, pairings, invitations, members, keys, signup, sso, mail, ops, box):
    router.include_router(family.router)

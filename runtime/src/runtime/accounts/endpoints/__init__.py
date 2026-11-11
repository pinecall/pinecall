"""The accounts router: whose a key is, the org's members, an invitation accepted, the keys, and the operator's orgs."""

from fastapi import APIRouter

from runtime.accounts.endpoints import identity, invitations, keys, members, ops

router = APIRouter()
for family in (identity, invitations, members, keys, ops):
    router.include_router(family.router)

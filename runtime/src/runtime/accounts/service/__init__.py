"""The accounts' rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.accounts.repository.members import Membership
from runtime.accounts.service.actor import check_agent, check_may_grant, scope_of_request, sees_every_copy
from runtime.accounts.service.emails import card_link
from runtime.accounts.service.invitations import Invitee, invite, reset_link, seat_founder
from runtime.accounts.service.key_cache import KeyCache
from runtime.accounts.service.keys import Issue, Issued, get_key, issue_key, issue_person_key, revoke_fingerprint
from runtime.accounts.service.members import (
    find_member_by_test_phone,
    find_membership,
    forget_test_phone,
    get_member,
    list_admin_addresses,
    list_members,
    seat_vouched,
    set_test_phone,
    take_seat,
)
from runtime.accounts.service.orgs import (
    SlugTaken,
    create_org,
    find_org,
    is_judged,
    judge_model_of,
    list_newborns,
    list_orgs,
    set_judge_model,
    set_judging,
    slug_of,
)
from runtime.accounts.service.passwords import hash_password
from runtime.accounts.service.people import (
    find_or_create_person,
    find_person,
    list_operator_addresses,
    memberships_of,
    password_matches,
    prove_mailbox,
)

__all__ = [
    "Invitee",
    "Issue",
    "Issued",
    "KeyCache",
    "Membership",
    "SlugTaken",
    "card_link",
    "check_agent",
    "check_may_grant",
    "create_org",
    "find_member_by_test_phone",
    "find_membership",
    "find_or_create_person",
    "find_org",
    "find_person",
    "forget_test_phone",
    "get_key",
    "get_member",
    "hash_password",
    "invite",
    "is_judged",
    "issue_key",
    "issue_person_key",
    "judge_model_of",
    "list_admin_addresses",
    "list_members",
    "list_newborns",
    "list_operator_addresses",
    "list_orgs",
    "memberships_of",
    "password_matches",
    "prove_mailbox",
    "reset_link",
    "revoke_fingerprint",
    "scope_of_request",
    "seat_founder",
    "seat_vouched",
    "sees_every_copy",
    "set_judge_model",
    "set_judging",
    "set_test_phone",
    "slug_of",
    "take_seat",
]

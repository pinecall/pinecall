"""Who a request is: the scope it acts in, the person behind its key, and the verified key itself."""

from dataclasses import dataclass
from datetime import datetime

from runtime.enums import Env, KeyScope, Role

# Holder value for org-owned rows: an empty string, not NULL, because it is part of primary keys.
THE_ORGS_OWN = ""


@dataclass(frozen=True, slots=True)
class Scope:
    """An org, one of its envs, and the holder a request acts as ("" for the org itself)."""

    org: str
    env: Env = Env.production
    holder: str = THE_ORGS_OWN


@dataclass(frozen=True, slots=True)
class Person:
    """The member a key was minted for, as its row stands now."""

    id: str
    org: str
    email: str
    name: str
    role: Role
    agents: frozenset[str] = frozenset()
    operator: bool = False
    production: bool = False
    # Whether the address was proven theirs: a key of an unproven address opens the org it was minted
    # in and no other, so a seat somebody made for an address never reaches what its owner joins later.
    verified: bool = False

    @property
    def opens_production(self) -> bool:
        """Whether this person may act in production; admins always may."""
        return self.role is Role.admin or self.production


@dataclass(frozen=True, slots=True)
class Actor:
    """The verified key behind a request, its person, and the scope it acts in."""

    key_id: str
    org: str
    env: Env
    scopes: frozenset[KeyScope]
    person: Person | None = None
    label: str | None = None
    expires_at: datetime | None = None
    holder: str = THE_ORGS_OWN

    @property
    def scope(self) -> Scope:
        """The scope this actor acts in."""
        return Scope(self.org, self.env, self.holder)

    @property
    def is_server(self) -> bool:
        """A key with no person: a server's token, the fleet's or the runner's."""
        return self.person is None

    @property
    def name(self) -> str:
        """Who to write down as the author of a change."""
        return self.person.name if self.person else (self.label or self.key_id)

    @property
    def asked_by(self) -> str:
        """The id a row keeps of who asked: the person's, or the key's when no person is behind it."""
        return self.person.id if self.person else self.key_id

    @property
    def is_fleet(self) -> bool:
        """Whether the key is an env's fleet, which serves every org of its env."""
        return KeyScope.fleet in self.scopes

    def opens(self, *scopes: KeyScope) -> bool:
        """Whether the key holds any of the scopes."""
        return any(scope in self.scopes for scope in scopes)

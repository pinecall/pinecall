"""The members table: a person's seat in an org, read with the person whose seat it is."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, func, literal, select, update

from runtime.accounts.models import Member, Person
from runtime.enums import ROLE_SCOPES, MemberStatus, Role
from runtime.kit.repository import Repository


# A seat says little without its person: whether the address was proven and whether they run the box are
# the person's. Flat, as every answer that shows a member reads one.
@dataclass(frozen=True, slots=True)
class Membership:
    """A member of an org and the person they are."""

    member: Member
    person: Person

    @property
    def id(self) -> str:
        """The member's id: what a key's subject and a path name."""
        return self.member.id

    @property
    def org(self) -> str:
        """The org the seat is in."""
        return self.member.org

    @property
    def email(self) -> str:
        """The person's address."""
        return self.person.email

    @property
    def name(self) -> str:
        """What the org calls them."""
        return self.member.name

    @property
    def role(self) -> Role:
        """Their role in the org."""
        return self.member.role

    @property
    def agents(self) -> list[str]:
        """The agents they work on, sorted; none means every agent of the org."""
        return sorted(self.member.agents)

    @property
    def status(self) -> MemberStatus:
        """Whether they may sign in to the org."""
        return self.member.status

    @property
    def scopes(self) -> list[str]:
        """The scopes their role presets, sorted."""
        return sorted(scope.value for scope in ROLE_SCOPES[self.member.role])

    @property
    def operator(self) -> bool:
        """Whether the person runs the box."""
        return self.person.operator

    @property
    def production(self) -> bool:
        """Whether they may act in production; admins always may."""
        return self.member.opens_production

    @property
    def verified(self) -> bool:
        """Whether the person's address was proven theirs."""
        return self.person.verified


class MemberRepository(Repository[Member]):
    """Members within an org, and a person's seats across orgs."""

    model = Member

    async def find(self, org: str, member_id: str) -> Member | None:
        """By id, within the org."""
        return await self.one_or_none(self.statement().where(Member.org == org, Member.id == member_id))

    async def find_by_email(self, org: str, email: str) -> Member | None:
        """By address, within the org."""
        return await self.one_or_none(self.statement().where(Member.org == org, Member.email == email))

    async def find_membership(self, member_id: str) -> Membership | None:
        """The member and their person by the member's id, whatever the org. Read box-wide by the caller."""
        return await self._one_membership(_memberships().where(Member.id == member_id))

    async def find_membership_in(self, org: str, member_id: str) -> Membership | None:
        """The member and their person by the member's id, within the org."""
        return await self._one_membership(_memberships().where(Member.org == org, Member.id == member_id))

    async def find_membership_by_email(self, org: str, email: str) -> Membership | None:
        """The member and their person by address, within the org."""
        return await self._one_membership(_memberships().where(Member.org == org, Member.email == email))

    async def list_memberships(self, org: str) -> Sequence[Membership]:
        """The org's people, oldest first, the disabled ones too."""
        statement = _memberships().where(Member.org == org).order_by(Member.created_at, Member.id)
        return [Membership(member, person) for member, person in (await self.session.execute(statement)).all()]

    async def list_of_person(self, person_id: str) -> Sequence[Member]:
        """Every seat of the person, oldest first. Read box-wide by the caller."""
        return await self.all(self.statement().where(Member.person == person_id).order_by(Member.created_at, Member.id))

    async def list_active_admins(self, org: str) -> Sequence[Member]:
        """The org's admins who may sign in, oldest first."""
        statement = self.statement().where(
            Member.org == org, Member.role == Role.admin, Member.status == MemberStatus.active
        )
        return await self.all(statement.order_by(Member.created_at, Member.id))

    async def find_by_test_phone(self, phone: str) -> Member | None:
        """Whose phone this is, in whatever org. Read box-wide by the caller."""
        return await self.one_or_none(self.statement().where(Member.test_phone == phone))

    async def list_with_test_phones(self) -> Sequence[Member]:
        """Everyone who said which phone is theirs, in every org. Read box-wide by the caller."""
        return await self.all(self.statement().where(Member.test_phone.is_not(None)).order_by(Member.id))

    async def release_test_phone(self, phone: str) -> None:
        """A phone is one person's: whoever had it before has it no more. Run box-wide by the caller."""
        await self.change(update(Member).where(Member.test_phone == phone).values(test_phone=None, test_agent=None))

    async def count_seated(self, org: str) -> int:
        """Every member not disabled holds a seat."""
        return await self.count(self.statement().where(Member.org == org, Member.status != MemberStatus.disabled))

    async def count_other_active_admins(self, org: str, member_id: str) -> int:
        """Active admins of the org other than this one."""
        return await self.count(
            self.statement().where(
                Member.org == org,
                Member.id != member_id,
                Member.role == Role.admin,
                Member.status == MemberStatus.active,
            )
        )

    async def lock_org(self, org: str) -> None:
        """A transaction-long advisory lock on the org: the seat count and the insert go together."""
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(literal(org)))))

    async def _one_membership(self, statement: Select[Member, Person]) -> Membership | None:
        found = (await self.session.execute(statement)).one_or_none()
        if found is None:
            return None
        member, person = found
        return Membership(member, person)


# A member whose person is not written yet (a row the cutover's backfill has not reached) is not read:
# it opens nothing and is listed nowhere, until the backfill gives it its person.
def _memberships() -> Select[Member, Person]:
    return select(Member, Person).join(Person, Member.person == Person.id)

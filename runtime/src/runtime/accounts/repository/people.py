"""The people table: a person by their address, across every org that seats them."""

from collections.abc import Sequence

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from runtime.accounts.models import Member, Person
from runtime.enums import MemberStatus
from runtime.kit.repository import Repository


class PersonRepository(Repository[Person]):
    """People by id and by address. The table names no org: every statement reads the whole box."""

    model = Person

    async def find(self, person_id: str) -> Person | None:
        """By id, or None."""
        return await self.one_or_none(self.statement().where(Person.id == person_id))

    async def find_by_email(self, email: str) -> Person | None:
        """By address, or None."""
        return await self.one_or_none(self.statement().where(Person.email == email))

    # One statement, so two invitations of the same new address at once make one person: the second
    # insert finds the address taken, and both read the row that stands.
    async def find_or_create(self, person_id: str, email: str) -> Person:
        """The person of the address, made under the id given when the address is new to the box."""
        made = insert(Person).values(id=person_id, email=email).on_conflict_do_nothing(index_elements=[Person.email])
        await self.session.execute(made)
        return await self.one(self.statement().where(Person.email == email))

    async def list_active_operators(self) -> Sequence[Person]:
        """The box's operators who may sign in somewhere, oldest first. Read box-wide by the caller."""
        seated = exists().where(Member.person == Person.id, Member.status == MemberStatus.active)
        return await self.all(self.statement().where(Person.operator, seated).order_by(Person.created_at, Person.id))

    async def delete_if_orphan(self, person_id: str) -> bool:
        """Forget the person once no org seats them; whether they went. Run box-wide by the caller."""
        seated = exists().where(Member.person == Person.id)
        return await self.change(delete(Person).where(Person.id == person_id, ~seated)) > 0

    async def delete_orphans(self) -> int:
        """Forget every person no org seats; how many went. Run box-wide by the caller."""
        seated = select(Member.person).where(Member.person.is_not(None))
        return await self.change(delete(Person).where(Person.id.not_in(seated)))

"""The invitations table: the links that seat a person or set their password again."""

from sqlalchemy import update

from runtime.accounts.models import Invitation
from runtime.kit.repository import Repository
from runtime.kit.time import now


class InvitationRepository(Repository[Invitation]):
    """The links that seat a person or reset their password."""

    model = Invitation

    async def spend(self, token_hash: str) -> Invitation | None:
        """Mark the link spent, once; None when dead, spent or unknown."""
        statement = (
            update(Invitation)
            .where(
                Invitation.token_hash == token_hash,
                Invitation.spent_at.is_(None),
                Invitation.expires_at > now(),
            )
            .values(spent_at=now())
            .returning(Invitation)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def spend_open_of(self, member_id: str) -> None:
        """Every open link of the member is spent: a new one replaces them."""
        await self.change(
            update(Invitation)
            .where(Invitation.member == member_id, Invitation.spent_at.is_(None))
            .values(spent_at=now())
        )

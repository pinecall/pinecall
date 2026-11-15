"""The api_keys table: keys by fingerprint and by org, revoked with every copy made of them."""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import ColumnElement, delete, select, update

from runtime.accounts.models import ApiKey, Member
from runtime.kit.repository import Repository
from runtime.kit.time import now


class ApiKeyRepository(Repository[ApiKey]):
    """API keys by fingerprint and by org."""

    model = ApiKey

    async def find(self, key_id: str) -> ApiKey | None:
        """By id, or None."""
        return await self.one_or_none(self.statement().where(ApiKey.id == key_id))

    async def find_live_by_hash(self, hash_: str) -> ApiKey | None:
        """The key with this fingerprint unless revoked; expired keys are returned, so the refusal can say so."""
        return await self.one_or_none(self.statement().where(ApiKey.hash == hash_, ApiKey.revoked_at.is_(None)))

    async def find_by_hash_in_org(self, org: str, hash_: str) -> ApiKey | None:
        """The org's key with this fingerprint, revoked or not."""
        return await self.one_or_none(self.statement().where(ApiKey.org == org, ApiKey.hash == hash_))

    async def list_of_org(self, org: str) -> Sequence[ApiKey]:
        """Every key of the org, oldest first, the revoked ones too."""
        return await self.all(self.statement().where(ApiKey.org == org).order_by(ApiKey.created_at, ApiKey.id))

    async def touch(self, key: ApiKey, *, kept: timedelta | None = None) -> None:
        """Note the key was used, at most once a minute; a key kept only while used lives that long from now."""
        last, moment = key.last_used_at, now()
        if last is not None and last >= moment - timedelta(minutes=1):
            return
        if kept is None:
            await self.update(key, last_used_at=moment)
        else:
            await self.update(key, last_used_at=moment, expires_at=moment + kept)

    async def revoke_tree(self, hash_: str) -> list[str]:
        """Revoke the key and every copy made of it, however deep; the fingerprints stopped."""
        roots = (
            select(ApiKey.id).where(ApiKey.hash == hash_, ApiKey.revoked_at.is_(None)).cte("stopped", recursive=True)
        )
        copies = select(ApiKey.id).where(ApiKey.parent == roots.c.id, ApiKey.revoked_at.is_(None))
        stopped = roots.union(copies)
        return await self._revoke(ApiKey.id.in_(select(stopped.c.id)))

    async def revoke_of_member(self, member_id: str, *, keep: str | None = None) -> list[str]:
        """Every live key minted for the member is revoked, but the one kept; the rows stay. The fingerprints."""
        theirs = ApiKey.subject == member_id
        return await self._revoke(theirs if keep is None else theirs & (ApiKey.id != keep))

    async def revoke_of_person(self, person_id: str, *, keep: str | None = None) -> list[str]:
        """Every live key of any seat of the person is revoked, but the one kept. Run box-wide by the caller."""
        theirs = ApiKey.subject.in_(select(Member.id).where(Member.person == person_id))
        return await self._revoke(theirs if keep is None else theirs & (ApiKey.id != keep))

    async def rename_of_member(self, member_id: str, name: str) -> None:
        """Every live key minted for the member says their name as it is now."""
        await self.change(
            update(ApiKey).where(ApiKey.subject == member_id, ApiKey.revoked_at.is_(None)).values(name=name)
        )

    async def delete_of_org(self, org: str) -> int:
        """Forget every key of the org; how many went."""
        return await self.change(delete(ApiKey).where(ApiKey.org == org))

    async def _revoke(self, which: ColumnElement[bool]) -> list[str]:
        statement = update(ApiKey).where(which, ApiKey.revoked_at.is_(None)).values(revoked_at=now())
        return list((await self.session.execute(statement.returning(ApiKey.hash))).scalars().all())

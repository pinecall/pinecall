"""The recording_keys table: each call's own recording key, sealed."""

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from runtime.compliance.models import RecordingKey
from runtime.kit.repository import Repository


class RecordingKeyRepository(Repository[RecordingKey]):
    """A recording's own key, sealed; erased with the call."""

    model = RecordingKey

    # The insert is the mint: of two asks at once, or a retry, the first key stands and is the
    # answer. Asked for another org's call, nothing: the update's WHERE fails and nothing returns.
    async def mint(self, call: str, org: str, sealed: str) -> str | None:
        """The call's sealed key, this one or the one minted before; None for another org's call."""
        statement = (
            insert(RecordingKey)
            .values(call=call, org=org, sealed=sealed)
            .on_conflict_do_update(
                index_elements=["call"],
                set_={"call": RecordingKey.call},
                where=RecordingKey.org == org,
            )
            .returning(RecordingKey.sealed)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def find(self, call: str) -> RecordingKey | None:
        """The call's key row, or None when it was never recorded sealed."""
        return await self.one_or_none(self.statement().where(RecordingKey.call == call))

    async def delete_of_org(self, org: str) -> int:
        """Forget every key of the org's calls; how many went."""
        return await self.change(delete(RecordingKey).where(RecordingKey.org == org))

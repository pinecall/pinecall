"""A recording's key: minted once per call and sealed, read to open the audio, gone with its call."""

import base64

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.compliance.repository.recordings import RecordingKeyRepository
from runtime.kit.crypto import Vault
from runtime.kit.sealed_file import new_key


async def mint_recording_key(session: AsyncSession, vault: Vault, org: str, call: str) -> bytes | None:
    """The call's recording key, made now or before; None for another org's call."""
    fresh = vault.seal(base64.urlsafe_b64encode(new_key()).decode())
    sealed = await RecordingKeyRepository(session).mint(call, org, fresh)
    return None if sealed is None else base64.urlsafe_b64decode(vault.open(sealed))


async def recording_key_of(session: AsyncSession, vault: Vault, call: str) -> bytes | None:
    """The call's recording key; None when it was never recorded sealed."""
    row = await RecordingKeyRepository(session).find(call)
    return None if row is None else base64.urlsafe_b64decode(vault.open(row.sealed))


# No foreign key reaches a key from its org (`recording_keys.org` is text): until 2026-11 an org erased
# left the keys of its calls behind. The org's erasure calls this; a call's own erasure takes its row.
async def delete_recording_keys(session: AsyncSession, org: str) -> int:
    """Forget the key of every call of an org that is being erased; how many went."""
    return await RecordingKeyRepository(session).delete_of_org(org)

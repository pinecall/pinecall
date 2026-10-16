"""Each distinct block of prompt an org's calls were told, kept once under its hash, read back."""

from collections import OrderedDict
from collections.abc import Collection

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import block_hash
from pinecall_runtime.agents.repository import PromptRepository

# The texts this process wrote, remembered so a block is written once and not per call.
REMEMBERED = 10_000


class PromptCache:
    """The blocks this gateway process has kept already, by org and hash; not durable on purpose."""

    def __init__(self) -> None:
        self._kept: OrderedDict[tuple[str, str], None] = OrderedDict()

    async def keep(self, session: AsyncSession, org: str, text: str) -> None:
        """Keep the text under its hash for the org, once; an empty block is nothing to keep."""
        key = (org, block_hash(text))
        if not text or key in self._kept:
            return
        await PromptRepository(session).keep(org, key[1], text)
        self._kept[key] = None
        if len(self._kept) > REMEMBERED:
            self._kept.popitem(last=False)


async def texts_of(session: AsyncSession, org: str, hashes: Collection[str]) -> dict[str, str]:
    """The org's texts of these hashes, those it kept."""
    return await PromptRepository(session).texts_of(org, list(hashes))

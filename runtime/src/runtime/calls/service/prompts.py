"""Each distinct block of prompt an org's calls were told, kept once under its hash, read back."""

from collections import OrderedDict
from collections.abc import Collection

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.calls.repository.prompts import PromptRepository
from runtime.kit.text import sha256_of

# The texts this process wrote, remembered so a block is written once and not per call.
REMEMBERED = 10_000


# What judging asks a call's prompt of (`judging.service.panel.PromptTexts`), and what the live
# side keeps each block with as a call is told it.
class Prompts:
    """The blocks this gateway process has kept already, by org and hash; not durable on purpose."""

    def __init__(self) -> None:
        """Start having kept nothing."""
        self._kept: OrderedDict[tuple[str, str], None] = OrderedDict()

    async def keep(self, session: AsyncSession, org: str, text: str) -> None:
        """Keep the text under its hash for the org, once; an empty block is nothing to keep."""
        key = (org, sha256_of(text))
        if not text or key in self._kept:
            return
        await PromptRepository(session).keep(org, key[1], text)
        self._kept[key] = None
        if len(self._kept) > REMEMBERED:
            self._kept.popitem(last=False)

    async def texts_of(self, session: AsyncSession, org: str, hashes: Collection[str]) -> dict[str, str]:
        """The org's texts of these hashes, those it kept."""
        return await PromptRepository(session).texts_of(org, sorted(hashes))

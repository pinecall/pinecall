"""An agent's lexicon: how its voice says its words and the words its ears must know, read and written by scope."""

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.service import versions
from runtime.agents.service.declaration import agent_of
from runtime.agents.service.setting_names import refuse_what_the_class_sets
from runtime.agents.service.settings import History, Shown
from runtime.agents.service.versions import Written, scope_to_write
from runtime.agents.settings import Lexicon, check_lexicon

# The two settings a class may declare of the lexicon, by the names it declares them under.
SAYS = "says"
HEARS = "hears"


async def show_lexicon(session: AsyncSession, scope: Scope, slug: str) -> Shown[Lexicon]:
    """The agent's words as the key sees them: yours, the team's and production's, and which its class fixes."""
    kept = await versions.side_by_side(session, versions.LEXICON, scope, slug)
    agent = await agent_of(session, scope, slug)
    return Shown(scope.env, kept.yours, kept.team, kept.production, tuple(sorted(agent.fixed & {SAYS, HEARS})))


async def list_lexicon_history(
    session: AsyncSession, scope: Scope, slug: str, *, team: bool, limit: int
) -> History[Lexicon]:
    """One scope's versions of the agent's lexicon, newest first."""
    target = scope_to_write(scope, team=team)
    rows = await versions.list_history(session, versions.LEXICON, target, slug, limit=limit)
    return History(scope.env, target.holder, rows)


# A supervisor's key may write it: the words are theirs to fix.
async def put_lexicon(
    session: AsyncSession, scope: Scope, slug: str, wanted: Lexicon, written: Written, *, team: bool
) -> Shown[Lexicon]:
    """The agent's next lexicon in the key's scope or the team's; what its class declares is refused."""
    target = scope_to_write(scope, team=team)
    check_lexicon(wanted)
    newest = await versions.find_newest(session, versions.LEXICON, target, slug)
    before = Lexicon() if newest is None else newest.value
    moved = ((SAYS, wanted.said != before.said), (HEARS, wanted.heard != before.heard))
    changed = [name for name, is_new in moved if is_new]
    refuse_what_the_class_sets(await agent_of(session, target, slug), changed)
    # Nothing changes, nothing is written: a version says what moved.
    if changed or newest is None:
        await versions.add_version(session, versions.LEXICON, target, slug, wanted, written)
    return await show_lexicon(session, scope, slug)

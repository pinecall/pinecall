"""The live side's rows: the caller codes issued and claimed, each call's tries, and the ledger of room tokens."""

from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from runtime.enums import Env
from runtime.kit.repository import Repository
from runtime.kit.time import now
from runtime.live.models import CallerCode, CodeTry, Token


class CodeRepository(Repository[CallerCode]):
    """Every agent's live caller codes, and each call's count of tries."""

    model = CallerCode

    async def expire(self, agent: str, moment: float) -> Sequence[tuple[str, str | None]]:
        """Delete the agent's codes past their time; each code and the call that claimed it."""
        statement = (
            delete(CallerCode)
            .where(CallerCode.agent == agent, CallerCode.expires_at <= moment)
            .returning(CallerCode.code, CallerCode.claimed)
        )
        return [(str(code), claimed) for code, claimed in (await self.session.execute(statement)).all()]

    async def count_live(self, agent: str) -> int:
        """How many codes the agent has waiting."""
        return await self.count(self.statement().where(CallerCode.agent == agent))

    async def keep(self, row: CallerCode) -> bool:
        """Insert the code; False when the agent has that code already."""
        try:
            async with self.session.begin_nested():
                await self.add(row)
        except IntegrityError:
            return False
        return True

    async def find(self, agent: str, code: str) -> CallerCode | None:
        """The code as it stands, or None for one nobody issued."""
        return await self.one_or_none(self.statement().where(CallerCode.agent == agent, CallerCode.code == code))

    # Each try counted in one statement, so two gateways serving one call count both.
    async def count_try(self, call: str, moment: float) -> int:
        """One more try of the call, and how many it made."""
        statement = insert(CodeTry).values(call=call, tries=1, first_at=moment)
        statement = statement.on_conflict_do_update(index_elements=[CodeTry.call], set_={"tries": CodeTry.tries + 1})
        return int((await self.session.execute(statement.returning(CodeTry.tries))).scalar_one())

    async def forget_tries_before(self, since: float) -> None:
        """Drop the counts of tries older than that."""
        await self.session.execute(delete(CodeTry).where(CodeTry.first_at <= since))

    # Taken by one call: the second finds it claimed and gets nothing.
    async def take(self, agent: str, code: str, env: Env, call: str, moment: float) -> CallerCode | None:
        """Tie the code to the call; None when it is nobody's, dead or taken."""
        statement = (
            update(CallerCode)
            .where(
                CallerCode.agent == agent,
                CallerCode.code == code,
                CallerCode.env == env,
                CallerCode.claimed.is_(None),
                CallerCode.expires_at > moment,
            )
            .values(claimed=call)
            .returning(CallerCode)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def count_tries(self) -> int:
        """How many calls tried a code lately; for the doctor."""
        return int((await self.session.execute(select(func.count()).select_from(CodeTry))).scalar_one())


class TokenRepository(Repository[Token]):
    """The ledger of room tokens, each spent once when its call opens."""

    model = Token

    async def spend(self, call: str, org: str, env: Env, agent: str) -> bool:
        """Spend the call's token in this scope, once; False when none matched."""
        statement = (
            update(Token)
            .where(
                Token.call == call,
                Token.spent_at.is_(None),
                Token.org == org,
                Token.agent == agent,
                or_(Token.env.is_(None), Token.env == env),
            )
            .values(spent_at=now())
            .returning(Token.call)
        )
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

    async def find(self, call: str) -> Token | None:
        """The ledger's row for the call, spent or not."""
        return await self.one_or_none(self.statement().where(Token.call == call))

    async def delete_of_org(self, org: str) -> int:
        """Forget every token minted for an org that is being erased; how many went. Run box-wide by the caller."""
        return await self.change(delete(Token).where(Token.org == org))

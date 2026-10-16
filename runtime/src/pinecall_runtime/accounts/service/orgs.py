"""Orgs: made with the limits the box gives a newborn, found by id or slug, removed whole."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.accounts.models import Org
from pinecall_runtime.accounts.repository import OrgRepository
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.crypto import random_id
from pinecall_runtime.kit.text import parse_slug
from pinecall_runtime.wire.parts import ModelConfig

ID_PREFIX = "org_"


class SlugTaken(Conflict):
    """Another org has the slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"{slug} is taken: pick another name for the org")


class NoSuchOrg(NotFound):
    """No org by that id or slug."""

    def __init__(self, named: str) -> None:
        super().__init__(f"no org answers to {named!r}")


async def create_org(session: AsyncSession, slug: str, name: str, *, already: int = 0) -> Org:
    """Make an org with the quotas the box's admission gives it; `already` is the founder's org count."""
    from pinecall_runtime.billing import service as billing

    orgs = OrgRepository(session)
    parse_slug(slug)
    if await orgs.get(slug) is not None:
        raise SlugTaken(slug)
    org = Org(id=random_id(ID_PREFIX, 6), slug=slug, name=name)
    await orgs.add(org)
    await billing.give_first_quotas(session, org.id, already=already)
    return org


async def get_org(session: AsyncSession, named: str) -> Org:
    """The org by id or slug; NotFound otherwise."""
    org = await OrgRepository(session).get(named)
    if org is None:
        raise NoSuchOrg(named)
    return org


async def find_org(session: AsyncSession, named: str) -> Org | None:
    """The org by id or slug, or None."""
    return await OrgRepository(session).get(named)


async def list_orgs(session: AsyncSession) -> Sequence[Org]:
    """Every org, oldest first."""
    return await OrgRepository(session).list_all()


async def delete_org(session: AsyncSession, org_id: str) -> bool:
    """Forget the org and, by the foreign keys' cascade, everything it holds."""
    orgs = OrgRepository(session)
    org = await orgs.one_or_none(orgs.statement().where(Org.id == org_id))
    if org is None:
        return False
    await orgs.delete(org)
    return True


async def slug_of(session: AsyncSession, org_id: str) -> str:
    """The org's slug, or its id when the row is gone."""
    org = await OrgRepository(session).get(org_id)
    return org_id if org is None else org.slug


async def is_judged(session: AsyncSession, org: str) -> bool:
    """Whether the org's calls are judged at hang-up; an org nobody finds is."""
    found = await find_org(session, org)
    return found is None or found.is_judged


async def set_judging(session: AsyncSession, org: str, *, on: bool) -> None:
    """Turn the org's judging on or off."""
    await OrgRepository(session).update(await get_org(session, org), judging=on)


async def judge_model_of(session: AsyncSession, org: str) -> ModelConfig | None:
    """The model the org's calls are judged on, as it was named; None: the platform's."""
    found = await find_org(session, org)
    if found is None or found.judge_model is None:
        return None
    return ModelConfig.model_validate(found.judge_model)


async def set_judge_model(session: AsyncSession, org: str, model: ModelConfig | None) -> None:
    """Name the model the org's calls are judged on, or None for the platform's."""
    kept = None if model is None else model.model_dump(mode="json", exclude_none=True)
    await OrgRepository(session).update(await get_org(session, org), judge_model=kept)

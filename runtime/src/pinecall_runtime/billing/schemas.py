"""The bodies of the billing endpoints: an org's quotas, and what it may use against what it used."""

from typing import Self

from pydantic import Field

from pinecall_runtime.billing.service import Quotas
from pinecall_runtime.enums import Env
from pinecall_runtime.kit.schemas import Row, Schema
from pinecall_runtime.wire.parts import QuotaName


# The same shape read and written: a limit left out is none, and `lends` null lends everything.
class OrgQuotas(Schema):
    """An org's limits in one env, by name; null is no limit, and `lends` comes back sorted."""

    limits: dict[QuotaName, int | None] = Field(default_factory=dict[QuotaName, int | None])
    budget_usd: int | None = None
    lends: list[str] | None = None

    @classmethod
    def of(cls, quotas: Quotas) -> Self:
        """An org's limits as the endpoints send them, `lends` sorted."""
        return cls(
            limits=dict(quotas.limits),
            budget_usd=quotas.budget_usd,
            lends=None if quotas.lends is None else sorted(quotas.lends),
        )


class PutQuotasRequest(Schema):
    """PUT /v1/ops/orgs/{named}/quotas: which env, and the whole set for it."""

    env: Env
    quotas: OrgQuotas


class Limit(Row):
    """One quota: the limit the org was given, and how much of it is used."""

    limit: int | None
    used: float


class Limits(Row):
    """GET /v1/limits: what the key's org may use in the env and has used, and its lends."""

    minutes: Limit
    messages: Limit
    llm_tokens: Limit
    concurrent_calls: Limit
    agents: Limit
    seats: Limit
    numbers: Limit
    # This month's judges that answered on the platform's key, and calls a simulated caller played.
    evals: Limit
    simulations: Limit
    lends: list[str] | None
    billing_url: str | None
    world: Env

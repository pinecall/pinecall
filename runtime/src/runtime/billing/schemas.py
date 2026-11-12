"""The bodies of the billing endpoints: an org's quotas, what a newborn org is given, a quota against its use."""

from typing import Any, Self

from pydantic import Field

from runtime.enums import Env
from runtime.kit.schemas import Row, Schema
from runtime.wire.parts import QuotaName


# The same shape read and written: a limit left out is none, and `lends` null lends everything.
class OrgQuotas(Schema):
    """An org's limits in one env, by name; null is no limit, and `lends` comes back sorted."""

    limits: dict[QuotaName, int | None] = Field(default_factory=dict[QuotaName, int | None])
    budget_usd: int | None = None
    lends: list[str] | None = None
    # How the org's simulations are shaped; null is the platform's own. Read here, written by
    # `PUT …/simulating`: a quotas body leaves them as they stand.
    simulations_at_once: int | None = None
    comparison_calls: int | None = None

    # Read off billing's `Quotas` by its attributes: a schema never imports its domain's service.
    @classmethod
    def of(cls, kept: Any, /) -> Self:
        """An org's quotas in one env as they are answered: `lends` sorted."""
        lends = kept.lends
        return cls(
            limits=dict(kept.limits),
            budget_usd=kept.budget_usd,
            lends=None if lends is None else sorted(lends),
            simulations_at_once=kept.simulations_at_once,
            comparison_calls=kept.comparison_calls,
        )

    def limits_named(self) -> dict[QuotaName, int | None]:
        """Every limit the body names, the budget among them."""
        return {**self.limits, "budget_usd": self.budget_usd}


class PutSimulatingRequest(Schema):
    """PUT /v1/ops/orgs/{named}/simulating: which env, and its simulations' shape; null is the platform's own."""

    env: Env
    simulations_at_once: int | None = Field(default=None, ge=0, le=200)
    comparison_calls: int | None = Field(default=None, ge=0, le=500)


class PutQuotasRequest(Schema):
    """PUT /v1/ops/orgs/{named}/quotas: which env, and the whole set for it."""

    env: Env
    quotas: OrgQuotas


# The body the operator's billing writes and reads: each env's quotas flat, as the box keeps them.
class EnvQuotas(Schema):
    """One env's quotas of a newborn org: every limit by name, the lends, the simulations' shape."""

    minutes: int | None = None
    messages: int | None = None
    agents: int | None = None
    concurrent_calls: int | None = None
    memory_facts: int | None = None
    knowledge_chunks: int | None = None
    numbers: int | None = None
    seats: int | None = None
    llm_tokens: int | None = None
    hosted_apps: int | None = None
    evals: int | None = None
    simulations: int | None = None
    budget_usd: int | None = None
    lends: list[str] | None = None
    simulations_at_once: int | None = None
    comparison_calls: int | None = None


class Admission(Schema):
    """GET and PUT /v1/ops/admission: what a newborn org is given in each env, a first org and a later one."""

    first: dict[Env, EnvQuotas] = Field(default_factory=dict[Env, EnvQuotas])
    later: dict[Env, EnvQuotas] | None = None


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
    # What the org keeps now (facts, chunks, the apps the box hosts), and the dollars its calls cost this
    # month in both envs together: every quota an operator can set is shown, set or not.
    memory_facts: Limit
    knowledge_chunks: Limit
    hosted_apps: Limit
    budget_usd: Limit
    lends: list[str] | None
    billing_url: str | None
    world: Env

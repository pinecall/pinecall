"""A comparison's plan as its row keeps it: what was asked, how its placing stands, what a take-up needs."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.enums import KeyScope
from runtime.evals.models import Comparison as ComparisonRow
from runtime.evals.repository import ComparisonRepository
from runtime.kit.text import JsonObject, a_list, a_mapping

# The gateway that plays a comparison says so this often, from its first call to its last call's end.
# One that has not said so for two of them was left by its gateway, and another takes it up; a reader
# calls it left after three, which a comparison that can be taken up never reaches.
STILL_PLACING_EVERY_S = 20.0
PICKED_UP_AFTER_S = 2 * STILL_PLACING_EVERY_S
LEFT_AFTER_S = 3 * STILL_PLACING_EVERY_S


@dataclass(frozen=True, slots=True)
class Pair:
    """One call a comparison is to place: the caller, and the agent's values it rings under."""

    persona: str
    against: JsonObject


@dataclass(frozen=True, slots=True)
class Refused:
    """One call a comparison could not place, and the refusal in the gateway's words."""

    persona: str
    against: JsonObject
    why: str


# A comparison is coroutines of the gateway that took its request, gone with that process: until
# 2026-11-24 a release ended it and said so to nobody, the calls that waited never placed and the
# command that followed it never returning. What another gateway needs to go on is kept with the plan:
# what each call is placed with (`wanted`, as a call's facts keep it), what each caller was briefed to
# phone about, the key that asked, and the calls played again in a lost one's place.
@dataclass
class Plan:
    """A comparison as it was asked for, and how its placing stands."""

    comparison: str
    agent: str
    scope: Scope
    spoken: bool
    personas: list[str]
    against: list[JsonObject]
    repeats: int
    started_at: float
    waiting: int = 0
    refused: list[Refused] = field(default_factory=list[Refused])
    heard_at: float = 0.0
    # False for a comparison made before plans were kept: it is what its calls say.
    kept: bool = True
    wanted: JsonObject | None = None
    # Each caller's scenario as it was briefed, `{goal, facts}`; None for a caller of the agent's own.
    briefs: dict[str, JsonObject | None] = field(default_factory=dict[str, JsonObject | None])
    by: JsonObject | None = None
    # The calls another one was placed for: lost with the gateway that played them, no row of the table.
    replaced: list[str] = field(default_factory=list[str])
    # Whether its last call ended; None for a comparison made before 2026-11-24, which nobody takes up.
    done: bool | None = None

    @property
    def planned(self) -> int:
        """Every call the comparison was to place."""
        return len(self.personas) * len(self.against) * self.repeats

    def list_pairs(self) -> list[Pair]:
        """Every call to place, a round of every caller under every setup, then the next round."""
        once = [Pair(persona, values) for persona in self.personas for values in self.against]
        return once * self.repeats

    # The keys the release before 2026-11 writes and reads in `comparisons.document`, and the ones of
    # 2026-11-24 beside them, left out of a plan that carries none.
    def dump(self) -> JsonObject:
        """The plan as its row keeps it."""
        kept: JsonObject = {
            "voice": self.spoken,
            "personas": self.personas,
            "against": self.against,
            "repeats": self.repeats,
            "waiting": self.waiting,
            "refused": [{"persona": one.persona, "against": one.against, "why": one.why} for one in self.refused],
            "heard_at": self.heard_at,
        }
        if self.done is not None:
            kept |= {
                "wanted": self.wanted,
                "briefs": self.briefs,
                "by": self.by,
                "replaced": self.replaced,
                "done": self.done,
            }
        return kept


def is_left(plan: Plan, now: float) -> bool:
    """Whether calls still wait and the gateway placing them stopped saying so: they never will be placed."""
    return plan.waiting > 0 and now - plan.heard_at > LEFT_AFTER_S


def say_who_asked(actor: Actor) -> JsonObject:
    """The key a comparison was asked with, as its plan keeps it: enough to place its calls as that key's org."""
    return {"key_id": actor.key_id, "scopes": sorted(scope.value for scope in actor.scopes), "holder": actor.holder}


# The person behind the key is not kept: a comparison taken up is placed as the org's own server
# would place it, on the agent the person was let place it on.
def actor_of(plan: Plan) -> Actor:
    """Whoever asked for the comparison, to place the rest of its calls as."""
    by = plan.by or {}
    scopes = frozenset(KeyScope(str(scope)) for scope in _list_in(by.get("scopes")))
    return Actor(
        key_id=str(by.get("key_id", "")),
        org=plan.scope.org,
        env=plan.scope.env,
        scopes=scopes,
        holder=str(by.get("holder") or plan.scope.holder),
    )


async def keep_plan(sessions: async_sessionmaker[AsyncSession], plan: Plan) -> None:
    """Write the plan as it stands on its comparison's row."""
    async with sessions.begin() as session_:
        await ComparisonRepository(session_).put(
            ComparisonRow(
                id=plan.comparison,
                org=plan.scope.org,
                env=plan.scope.env,
                agent=plan.agent,
                started_at=plan.started_at,
                document=plan.dump(),
            )
        )


def read_plan(row: ComparisonRow, scope: Scope) -> Plan:
    """The plan a comparison's row keeps."""
    kept = row.document
    done = kept.get("done")
    return Plan(
        comparison=row.id,
        agent=row.agent,
        scope=scope,
        spoken=bool(kept.get("voice")),
        personas=[str(name) for name in _list_in(kept.get("personas"))],
        against=[dict(values) for values in _list_in(kept.get("against")) if a_mapping(values)],
        repeats=int(kept.get("repeats") or 1),
        started_at=row.started_at,
        waiting=int(kept.get("waiting") or 0),
        refused=[
            Refused(str(one.get("persona", "")), dict(_object_in(one.get("against"))), str(one.get("why", "")))
            for one in _list_in(kept.get("refused"))
            if a_mapping(one)
        ],
        heard_at=float(kept.get("heard_at") or 0.0),
        wanted=dict(_object_in(kept.get("wanted"))) or None,
        briefs={
            str(persona): dict(brief) if a_mapping(brief) else None
            for persona, brief in _object_in(kept.get("briefs")).items()
        },
        by=dict(_object_in(kept.get("by"))) or None,
        replaced=[str(call) for call in _list_in(kept.get("replaced"))],
        done=None if done is None else bool(done),
    )


def _object_in(value: object) -> Mapping[str, object]:
    return value if a_mapping(value) else {}


def _list_in(value: object) -> list[object]:
    return value if a_list(value) else []

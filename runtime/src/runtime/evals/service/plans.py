"""A comparison's plan as its row keeps it: what was asked, how its placing stands, what a take-up needs."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Actor, Scope
from runtime.enums import KeyScope
from runtime.evals.models import Comparison as ComparisonRow
from runtime.evals.repository import ComparisonRepository
from runtime.evals.service.validity import Validity
from runtime.kit.text import JsonObject, a_list, a_mapping

# The gateway that plays a comparison says so this often, from its first call to its last call's end.
# One that has not said so for two of them was left by its gateway, and another takes it up; a reader
# calls it left after three, which a comparison that can be taken up never reaches.
STILL_PLACING_EVERY_S = 20.0
PICKED_UP_AFTER_S = 2 * STILL_PLACING_EVERY_S
LEFT_AFTER_S = 3 * STILL_PLACING_EVERY_S
# A call that did not count (`validity`) is placed again, so that the table ends with the calls it
# planned: two more tries for each call planned of its caller and setup. Whatever breaks a third call
# of the same place breaks them all, and placing more would spend for nothing.
PLACED_AGAIN_AT_MOST = 2
NEVER_COUNTED = "no call of this caller on this setup counted, {times} placed again among them: {why}"
# A setup whose vendor refused one of its calls for good (no credit, a quota spent, a key or a model it
# does not know) is rung no more: its calls still waiting are refused in the vendor's words.
STOPPED = "no more calls are placed on this setup: {why}"
NO_ROOM = (
    "a comparison of this org places {most} calls at most and this one has: "
    "none is placed for a call that did not count ({why})"
)
# The values of a setup that name a vendor, each as `vendor` or `vendor/model`.
NAMES_A_VENDOR = ("llm", "stt", "tts", "realtime")


@dataclass(frozen=True, slots=True)
class Pair:
    """One call a comparison is to place: the caller, and the agent's values it rings under."""

    persona: str
    against: JsonObject


@dataclass(frozen=True, slots=True)
class Judged:
    """A call of a comparison that ended: whom it stands for, and whether it counted."""

    call: str
    pair: Pair
    validity: Validity
    # A vendor of the agent refused it in a way no retry changes: an account that cannot pay, a key or
    # a model it does not know.
    for_good: bool = False
    # The vendor that refused because its account cannot pay, "" otherwise: every setup that names it
    # is refused the same, whichever of them rang it first.
    unpaid: str = ""


@dataclass(frozen=True, slots=True)
class Uncounted:
    """A call that did not count, settled once: whom it stood for, and whether another was placed in its stead."""

    call: str
    pair: Pair
    placed_again: bool


@dataclass(frozen=True, slots=True)
class Stopped:
    """A setup a comparison rings no more, and why, in its vendor's words."""

    against: JsonObject
    why: str


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
    # The calls that did not count, each settled once: another placed in its stead, or its place
    # refused. Its row stays in the table, marked; the call placed after it stands for its place.
    uncounted: list[Uncounted] = field(default_factory=list[Uncounted])
    # The setups rung no more: a vendor refused one of their calls for good.
    stopped: list[Stopped] = field(default_factory=list[Stopped])

    @property
    def planned(self) -> int:
        """Every call the comparison was to place."""
        return len(self.personas) * len(self.against) * self.repeats

    def find_stop(self, against: JsonObject) -> Stopped | None:
        """The stop of this setup, with why it is rung no more; None while it is rung."""
        return next((one for one in self.stopped if one.against == against), None)

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
                "uncounted": [
                    {
                        "call": one.call,
                        "persona": one.pair.persona,
                        "against": one.pair.against,
                        "again": one.placed_again,
                    }
                    for one in self.uncounted
                ],
                "stopped": [{"against": one.against, "why": one.why} for one in self.stopped],
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
        uncounted=[
            Uncounted(
                str(one.get("call", "")),
                Pair(str(one.get("persona", "")), dict(_object_in(one.get("against")))),
                bool(one.get("again")),
            )
            for one in _list_in(kept.get("uncounted"))
            if a_mapping(one)
        ],
        stopped=[
            Stopped(dict(_object_in(one.get("against"))), str(one.get("why", "")))
            for one in _list_in(kept.get("stopped"))
            if a_mapping(one)
        ],
    )


def is_played(plan: Plan, now: float) -> bool:
    """Whether a gateway still plays the comparison: its last call has not ended, and one said so lately."""
    return plan.done is False and now - plan.heard_at <= LEFT_AFTER_S


def names_vendor(against: Mapping[str, object], vendor: str) -> bool:
    """Whether the setup rings this vendor by name, in any of its stages."""
    said = [str(against.get(stage) or "") for stage in NAMES_A_VENDOR]
    return any(value == vendor or value.startswith(f"{vendor}/") for value in said)


# A vendor that refused a call for good stops its setup: an account that cannot pay stops every setup
# that names that vendor, since the next call on any of them is refused the same.
def stop_refused(plan: Plan, ended: Sequence[Judged]) -> list[Stopped]:
    """Stop each setup a vendor refused one of these calls for good; the ones stopped now."""
    now: list[Stopped] = []
    for one in ended:
        invalid = one.validity.invalid
        if not one.for_good or invalid is None:
            continue
        named = [values for values in plan.against if one.unpaid and names_vendor(values, one.unpaid)]
        for against in [dict(one.pair.against), *named]:
            if plan.find_stop(against) is None:
                stopped = Stopped(dict(against), invalid.why)
                plan.stopped.append(stopped)
                now.append(stopped)
    return now


# What the calls that ended say to a comparison still played. A vendor that refused a call for good
# stops its setup, whose place is refused with every call of it still waiting (`find_stop`); a call
# that did not count for any other reason (its caller's own line, our side, a vendor that failed on
# its side) is placed again, unless its caller and setup were placed again as often as they may be or
# the comparison has placed all the calls its org lets one place, when its place is refused saying
# so. Each such call is settled once, in `uncounted`; what to place again is answered.
def settle_uncounted(plan: Plan, ended: Sequence[Judged], *, room: int, most: int) -> list[Pair]:
    """The calls to place again for those that did not count; the places refused and the setups stopped, on the plan."""
    stop_refused(plan, ended)
    settled = {one.call for one in plan.uncounted} | set(plan.replaced)
    again: list[Pair] = []
    for one in ended:
        invalid = one.validity.invalid
        if invalid is None or one.call in settled:
            continue
        settled.add(one.call)
        times = len([kept for kept in plan.uncounted if kept.pair == one.pair and kept.placed_again])
        stopped = plan.find_stop(one.pair.against)
        why: str | None = None
        if stopped is not None:
            why = STOPPED.format(why=stopped.why)
        elif times >= PLACED_AGAIN_AT_MOST * plan.repeats:
            why = NEVER_COUNTED.format(times=times, why=invalid.why)
        elif len(again) >= room:
            why = NO_ROOM.format(most=most, why=invalid.why)
        if why is None:
            again.append(one.pair)
        else:
            plan.refused.append(Refused(one.pair.persona, one.pair.against, why))
        plan.uncounted.append(Uncounted(one.call, one.pair, placed_again=why is None))
    return again


def _object_in(value: object) -> Mapping[str, object]:
    return value if a_mapping(value) else {}


def _list_in(value: object) -> list[object]:
    return value if a_list(value) else []

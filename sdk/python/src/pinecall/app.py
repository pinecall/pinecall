"""A voice app: the numbers a project answers, the agent that answers each, and what they share."""

import inspect
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pinecall import _config, _harness
from pinecall._handoff import Answering, taken_by
from pinecall.agent import Agent
from pinecall.errors import DeclarationRefused
from pinecall.flows import Flow
from pinecall.wire._names import JsonObject

A_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
A_NUMBER = re.compile(r"^\+[1-9]\d{6,14}$")
SECONDS = re.compile(r"^(\d+)s$")
# The type of the entry a line an agent logs is kept as: its own name is inside it.
A_LOGGED_LINE = "custom"

NOT_A_ZONE = "a voice app's timezone is an IANA zone, like America/Los_Angeles or Europe/Madrid"
NOT_A_NAME = "a voice app's name is lowercase letters, digits and dashes, like its project's folder"
NOT_A_NUMBER = "a line is a phone number with its country code, like +1 415 555 0134"
NOT_AN_AGENT = (
    "a line is answered by an agent, its class or its slug:"
    ' app.line(number, FrontDesk) or app.line(number, "front-desk")'
)
NOT_A_PAGE = 'a page is the folder its build writes, inside the project: app.page("ui/dist")'
NO_AGENT_FOR_A_PAGE = (
    "a page's visitors reach an agent: write a line before the page,"
    " or name one with app.page(dir, answers=FrontDesk)"
)
NOT_A_SILENCE = (
    'silence is after= in seconds (8, or "8s") and say= the words to a caller who went quiet'
)


@dataclass(frozen=True)
class Heard:
    """The call an entry belongs to, as a handler of the app is told it; `id` is None for none."""

    id: str | None
    agent: str


Hearing = Callable[[Heard, JsonObject], object]
"""A handler of `app.on`: the call, and what the entry carries; a `def` or an `async def`."""


@dataclass(frozen=True)
class Line:
    """One number of the app and who answers it."""

    number: str
    answers: type
    team: tuple[type, ...] = ()
    greeting: str | None = None
    chooses: Answering | None = None


@dataclass(frozen=True)
class Page:
    """The app's page: the built folder the platform serves, and the agent a visitor reaches."""

    dir: str
    answers: type


@dataclass
class VoiceApp:
    """A voice app. `line`, `rule`, `silence` and `page` return the app, so they chain."""

    name: str
    timezone: str | None = None
    lines: list[Line] = field(default_factory=list[Line])
    rules: list[str] = field(default_factory=list[str])
    paged: Page | None = None
    _silence: dict[str, object] | None = None
    _hearing: dict[str, list[Hearing]] = field(default_factory=dict[str, list[Hearing]])
    _starting: dict[str, list[Flow]] = field(default_factory=dict[str, list[Flow]])

    def line(
        self,
        number: str,
        answers: type | str | Answering,
        *,
        greeting: str | None = None,
        team: Sequence[type | str] = (),
        fallback: type | str | None = None,
    ) -> "VoiceApp":
        """Answer `number` with an agent: `app.line("+14155550134", "front-desk")`.

        An agent is named by its class or by its slug, its folder's name: an `app.py` that names
        slugs imports none of the agents' folders, which a dash keeps from being imported.

        Args:
            number: the number, with its country code.
            answers: the agent, or a function of the call that picks one of `team`.
            greeting: said as written when the call comes in, before any model runs.
            team: the agents the call may pass to; each says what it takes with `takes`.
            fallback: with a function, the agent the number is pointed at, which answers
                when the function picks nobody, fails or is late.
        """
        dialled = re.sub(r"[\s().-]", "", number)
        if not A_NUMBER.match(dialled):
            raise DeclarationRefused(NOT_A_NUMBER)
        if any(line.number == dialled for line in self.lines):
            raise DeclarationRefused(f"{dialled} is a line of {self.name} already")
        chooses, bound = _answering(answers, fallback, dialled)
        mates = _team_of(team, chooses, dialled)
        if greeting is not None and not greeting.strip():
            raise DeclarationRefused(f"the greeting of {dialled} is the words the call opens with")
        other = next(
            (one for one in self.lines if one.answers is bound and one.greeting != greeting), None
        )
        if other is not None:
            raise DeclarationRefused(
                f"{bound.__name__} answers {other.number} and {dialled}:"
                " both lines open with the same greeting, or with none"
            )
        self.lines.append(Line(dialled, bound, mates, greeting, chooses))
        return self

    def rule(self, rule: str) -> "VoiceApp":
        """A rule every agent of the app keeps: read into each one's prompt, and judged."""
        if not rule.strip():
            raise DeclarationRefused("a rule is a sentence every agent of the app keeps")
        self.rules.append(rule.strip())
        return self

    def on(self, name: str, handler: Hearing | Flow) -> "VoiceApp":
        """Run `handler` on every entry of that name on a call of the app's agents.

        An entry of a call's log by its type (`"call.ended"`), a line an agent logs by its name
        (`self.log("visit.booked", visit)`), or an event sent to the app. With a flow in place of
        the function, the entry starts a run of it, once, with what it carries.
        """
        if not name.strip():
            raise DeclarationRefused(
                "app.on takes the name of an entry and the function that hears it,"
                " or the flow it starts"
            )
        if isinstance(handler, Flow):
            other = next(
                (one for one in self.flows() if one.name == handler.name and one is not handler),
                None,
            )
            if other is not None:
                raise DeclarationRefused(
                    f"two flows of {self.name} are named {handler.name}:"
                    " a run is kept by its flow's name"
                )
            self._starting.setdefault(name, []).append(handler)
        else:
            self._hearing.setdefault(name, []).append(handler)
        return self

    def page(self, folder: str, *, answers: type | str | None = None) -> "VoiceApp":
        """The app's page: `app.page("ui/dist")`, served by the platform at the app's own name."""
        if isinstance(answers, str):
            answers = agent_of(answers, f"{self.name}'s page")
        cleaned = folder.removeprefix("./").rstrip("/")
        if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
            raise DeclarationRefused(NOT_A_PAGE)
        if self.paged is not None:
            raise DeclarationRefused(
                f"{self.name} has its page already, {self.paged.dir}: an app has one"
            )
        reached = answers or (self.lines[0].answers if self.lines else None)
        if reached is None or not _is_an_agent(reached):
            raise DeclarationRefused(NO_AGENT_FOR_A_PAGE)
        self.paged = Page(cleaned, reached)
        return self

    def silence(self, *, after: float | str, say: str, times: int | None = None) -> "VoiceApp":
        """What every agent of the app says to a caller who went quiet, and after how long."""
        seconds = _seconds_of(after)
        if seconds is None or not say.strip() or (times is not None and times < 1):
            raise DeclarationRefused(NOT_A_SILENCE)
        self._silence = {"says": [say], "after_s": seconds}
        if times is not None:
            self._silence["times"] = times
        return self

    def flows(self) -> list[Flow]:
        """Every flow the app starts, once each."""
        found: list[Flow] = []
        for flows in self._starting.values():
            found += [one for one in flows if one not in found]
        return found

    def started_by(self, name: str) -> list[Flow]:
        """The flows an entry of that name starts."""
        return list(self._starting.get(name, []))

    def named(self, kind: str, data: JsonObject) -> tuple[str, JsonObject]:
        """The name an entry is heard by and what it carries: a logged line by its own name."""
        if kind != A_LOGGED_LINE:
            return kind, data
        inner = data.get("data")
        return str(data.get("name", "")), inner if isinstance(inner, dict) else {}  # pyright: ignore[reportUnknownVariableType]

    async def heard(
        self, kind: str, call: str | None, agent: str, data: JsonObject,
        failed: Callable[[str, Exception], None],
    ) -> None:  # fmt: skip
        """Hand one entry to whoever asked for its name; one that raises is told to `failed`."""
        name, carried = self.named(kind, data)
        for handler in self._hearing.get(name, []):
            try:
                answered = handler(Heard(call, agent), carried)
                if inspect.isawaitable(answered):
                    await answered
            except Exception as thrown:  # noqa: BLE001 - one handler failing never stops the rest
                failed(name, thrown)

    def agents(self) -> list[type]:
        """Every agent class the app names, once each."""
        named = [one for line in self.lines for one in (line.answers, *line.team)]
        if self.paged is not None:
            named.append(self.paged.answers)
        return list(dict.fromkeys(named))

    def choosing(self, cls: type) -> Answering | None:
        """The function that picks who serves each call of the line `cls` is bound to."""
        return next(
            (line.chooses for line in self.lines if line.answers is cls and line.chooses), None
        )

    def team_of(self, cls: type) -> list[type]:
        """The agents a call of `cls` may pass between; empty for an agent of no team."""
        lines = [one for one in self.lines if one.team and (one.answers is cls or cls in one.team)]
        return list(dict.fromkeys(agent for one in lines for agent in (one.answers, *one.team)))

    def numbers_of(self, cls: type) -> list[str]:
        """The numbers `cls` answers."""
        return [line.number for line in self.lines if line.answers is cls]

    def declares(self, cls: type) -> dict[str, object]:
        """What the app adds to one agent's declaration; a setting both declare is refused."""
        added: dict[str, object] = {}
        greeting = next(
            (line.greeting for line in self.lines if line.answers is cls and line.greeting), None
        )
        if greeting is not None:
            _once(cls, "greeting", "its line's greeting", self.name)
            added["greeting"] = {"say": greeting}
        if cls not in self.agents():
            return added
        if self.timezone is not None:
            _once(cls, "timezone", "its own timezone", self.name)
            added["timezone"] = self.timezone
        if self.rules:
            added["judges"] = self._judging(cls)
        if self._silence is not None:
            _once(cls, "idle", "app.silence", self.name)
            added["idle"] = self._silence
        return added

    def _judging(self, cls: type) -> dict[str, object]:
        # The class's own judges stay, and each rule adds one: a declared list is the whole list.
        own = cast("dict[str, list[Any]]", _harness.harness_of(cls).get("judges") or {})
        asked = [
            _harness.own_judge(
                name=f"app-rule-{at}",
                asks=f'Did the agent keep this rule through the whole call: "{rule}"?',
            )
            for at, rule in enumerate(self.rules, start=1)
        ]
        return _harness.judges(on=own.get("on", []), own=[*own.get("own", []), *asked])


def voice_app(name: str, *, timezone: str | None = None) -> VoiceApp:
    """A voice app named as its project.

    ```python
    app = voice_app("brightside", timezone="America/Los_Angeles")
    ```

    Args:
        name: lowercase letters, digits and dashes, like the project's folder.
        timezone: the IANA zone the app's agents read their day and their clock in.
    """
    if not A_NAME.match(name):
        raise DeclarationRefused(NOT_A_NAME)
    if timezone is not None:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as wrong:
            raise DeclarationRefused(NOT_A_ZONE) from wrong
    return VoiceApp(name, timezone)


def agent_of(given: type | str, named_by: str) -> type:
    """The agent class a slug names, among those this process serves; a class is itself."""
    if not isinstance(given, str):
        return given
    found = _config.agent_named(given)
    if found is None:
        raise DeclarationRefused(
            f"{named_by} names {given}, and no agent here is served as {given}:"
            f" an agent's slug is its folder's name, agents/{given}/agent.py"
        )
    return found


def _answering(
    answers: type | str | Answering, fallback: type | str | None, dialled: str
) -> tuple[Answering | None, type]:
    # The function that chooses per call, when one answers the line, and the agent its number is
    # pointed at.
    if isinstance(answers, str):
        answers = agent_of(answers, dialled)
    if not callable(answers):
        raise DeclarationRefused(NOT_AN_AGENT)
    if isinstance(answers, type) and _is_an_agent(answers):
        return None, answers
    bound = None if fallback is None else agent_of(fallback, dialled)
    if bound is None or not _is_an_agent(bound):
        raise DeclarationRefused(
            f"{dialled}: a line whose answers is a function names its fallback,"
            " the agent the number is pointed at"
        )
    return answers, bound


def _team_of(
    team: Sequence[type | str], chooses: Answering | None, dialled: str
) -> tuple[type, ...]:
    mates = tuple(agent_of(mate, dialled) for mate in team)
    for mate in mates:
        if taken_by(mate) is None:
            raise DeclarationRefused(
                f"{mate.__name__} is of the team of {dialled} and says nothing of what it"
                ' takes: takes = "…"'
            )
    if chooses is not None and not mates:
        raise DeclarationRefused(
            f"{dialled}: a function answers with one of the line's team, and this line names none"
        )
    return mates


def _is_an_agent(given: object) -> bool:
    return isinstance(given, type) and issubclass(given, Agent)


def _once(cls: type, field_name: str, app_says: str, app: str) -> None:
    if field_name in vars(cls) or getattr(cls, field_name, None) is not None:
        raise DeclarationRefused(
            f"{cls.__name__} declares `{field_name}` and {app} declares {app_says}:"
            " keep one of the two"
        )


def _seconds_of(given: float | str) -> float | None:
    if isinstance(given, int | float):
        return float(given) if given > 0 else None
    found = SECONDS.match(given.strip())
    return None if found is None else float(found[1])

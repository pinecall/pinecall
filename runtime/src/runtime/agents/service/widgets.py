"""How the widget presents an agent: its class's look when it declares one, else the org's, else the widget's own."""

import re
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.agents.declaration import Agent
from runtime.agents.models import AgentWidget
from runtime.agents.repository import WidgetRepository
from runtime.agents.service.setting_names import refuse_what_the_class_sets
from runtime.exceptions import ValidationError
from runtime.wire.declared import WidgetLook
from runtime.wire.parts import WidgetTheme

LONGEST = {"title": 80, "tagline": 160, "greeting": 500, "accent": 40}
# The widget sets the accent as a CSS variable: nothing that could end the declaration passes.
A_COLOUR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+|(rgb|rgba|hsl|hsla|oklch)\([0-9.,%\s/a-z-]+\))$")


@dataclass(frozen=True, slots=True)
class Look:
    """How the widget presents the agent; None is the widget's own default."""

    title: str | None = None
    tagline: str | None = None
    greeting: str | None = None
    accent: str | None = None
    autostart: bool = False
    theme: WidgetTheme | None = None
    # True when the agent's class declares the look: a write is refused naming the class.
    fixed: bool = False


def check_look(look: Look) -> Look:
    """Refuse a look whose words run too long or whose accent is no CSS colour."""
    for name, longest in LONGEST.items():
        value: str | None = getattr(look, name)
        if value is not None and len(value) > longest:
            raise ValidationError(f"a widget's {name} is {longest} characters at most")
    if look.accent is not None and not A_COLOUR.match(look.accent):
        raise ValidationError(f"an accent is a CSS colour, not {look.accent!r}")
    return look


def look_of(declared: WidgetLook) -> Look:
    """The look as a class declares it."""
    return Look(
        title=declared.title,
        tagline=declared.tagline,
        greeting=declared.greeting,
        accent=declared.accent,
        autostart=declared.autostart,
        theme=declared.theme,
        fixed=True,
    )


# The widget is the agent's in an env, whoever holds it.
async def get_look(session: AsyncSession, scope: Scope, agent: Agent) -> Look:
    """How the agent's widget looks in the env: its class's when declared, else the row's, else the defaults."""
    if agent.declaration is not None and agent.declaration.widget is not None:
        return look_of(agent.declaration.widget)
    row = await WidgetRepository(session).find(scope.org, scope.env, agent.slug)
    return Look() if row is None else _look_of_row(row)


async def put_look(session: AsyncSession, scope: Scope, agent: Agent, look: Look) -> Look:
    """Replace how the agent's widget looks in the env, whole; refused while its class declares the look."""
    refuse_what_the_class_sets(agent, ["widget"])
    wanted = check_look(replace(look, fixed=False))
    await WidgetRepository(session).put(
        scope.org,
        scope.env,
        agent.slug,
        {
            "title": wanted.title,
            "tagline": wanted.tagline,
            "greeting": wanted.greeting,
            "accent": wanted.accent,
            "autostart": wanted.autostart,
            "theme": wanted.theme,
        },
    )
    return wanted


def _look_of_row(row: AgentWidget) -> Look:
    return Look(row.title, row.tagline, row.greeting, row.accent, row.autostart, _theme(row.theme))


def _theme(word: str | None) -> WidgetTheme | None:
    match word:
        case "auto" | "light" | "dark":
            return word
        case _:
            return None

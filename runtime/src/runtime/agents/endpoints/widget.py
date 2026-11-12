"""How an agent's widget looks: read by whoever may mint its token, replaced by whoever sets its pipeline."""

from fastapi import APIRouter

from runtime.agents import schemas
from runtime.agents.auth import PipelineKey, TalkKey, TheAgent
from runtime.agents.service import widgets
from runtime.postgres import Session

router = APIRouter()


# `talk`: whoever may mint the widget's token may read how it looks.
@router.get("/v1/agents/{slug}/widget")
async def get_widget(agent: TheAgent, actor: TalkKey, session: Session) -> schemas.WidgetSettings:
    """How the agent's widget looks in the key's env: its class's when declared, else the row's or the defaults."""
    look = await widgets.get_look(session, actor.scope, agent)
    return schemas.WidgetSettings.model_validate(look, from_attributes=True)


# `pipeline`: the same key that sets the agent's greeting and voice; refused while the class declares the look.
@router.put("/v1/agents/{slug}/widget")
async def put_widget(
    agent: TheAgent, body: schemas.WidgetSettings, actor: PipelineKey, session: Session
) -> schemas.WidgetSettings:
    """Replace how the widget looks, whole; a null field is the widget's own default."""
    wanted = widgets.Look(body.title, body.tagline, body.greeting, body.accent, body.autostart, body.theme)
    look = await widgets.put_look(session, actor.scope, agent, wanted)
    return schemas.WidgetSettings.model_validate(look, from_attributes=True)

"""The persona endpoints: Pinecall's switched and played, an agent's own, and the org's at once."""

from collections.abc import Sequence
from dataclasses import asdict

from fastapi import APIRouter

from runtime.agents.auth import TheAgent
from runtime.handles import TheVault
from runtime.judging import schemas
from runtime.judging.auth import EvalsKey
from runtime.judging.service import personas
from runtime.postgres import Session

router = APIRouter()


# Every agent's callers, the org's roster at once: one list for both envs, as an agent's is.
@router.get("/v1/personas")
async def list_every_persona(actor: EvalsKey, session: Session) -> schemas.PersonaList:
    """Every agent's callers, by agent and then by name."""
    return _list(await personas.list_of_org(session, actor.org))


# One list for both envs: a persona is test data, never heard by a customer. An agent whose class
# declares its personas lists the class's, each `fixed` (`owner: "class"` for its own).
@router.get("/v1/agents/{slug}/personas")
async def list_personas(agent: TheAgent, actor: EvalsKey, session: Session) -> schemas.PersonaList:
    """Pinecall's personas as switched for the agent, then the agent's own or its class's, by name."""
    return _list(await personas.list_personas(session, actor.org, agent))


# A model or a vendor this box lacks, or that nobody keyed, is refused when written, not on the call that
# plays it; while the agent's class declares its personas, nothing is written here (409 naming the class).
@router.put("/v1/agents/{slug}/personas/{name}")
async def put_persona(
    agent: TheAgent, name: str, body: schemas.PersonaRequest, actor: EvalsKey, vault: TheVault, session: Session
) -> schemas.PersonaList:
    """Write one of the agent's callers whole, or rename one from `was`; or switch Pinecall's."""
    wanted = personas.Wanted(
        **body.model_dump(exclude={"behavior"}), behavior=body.behavior, named=frozenset(body.model_fields_set)
    )
    return _list(await personas.write_persona(session, vault, actor.scope, agent, name, wanted, by=actor.asked_by))


@router.delete("/v1/agents/{slug}/personas/{name}")
async def delete_persona(agent: TheAgent, name: str, actor: EvalsKey, session: Session) -> schemas.PersonaList:
    """Forget one of the agent's callers; 404 for a name nobody wrote, 409 for Pinecall's or the class's."""
    return _list(await personas.delete_persona(session, actor.org, agent, name))


# A caller of the roster is its row by the same names: the persona's fields beside whose it is.
def _list(roster: Sequence[personas.RosterPersona]) -> schemas.PersonaList:
    rows = [schemas.PersonaRow.model_validate({**asdict(listed), **asdict(listed.persona)}) for listed in roster]
    return schemas.PersonaList(personas=rows)

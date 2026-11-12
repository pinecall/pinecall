"""What an org can run: the vendors installed and whose key runs each, a plugin's options, what the host advises."""

from typing import Annotated

from fastapi import APIRouter, Query

from runtime.enums import Stage
from runtime.handles import TheVault
from runtime.postgres import Session
from runtime.providers import schemas
from runtime.providers.auth import ProvidersKey
from runtime.providers.service import advice, plugin_options, readiness

router = APIRouter()


# The same for every key of an org: what is installed, and whose key would run each vendor.
@router.get("/v1/providers")
async def list_providers(actor: ProvidersKey, vault: TheVault, session: Session) -> schemas.ProvidersResponse:
    """Every vendor this build runs and how this org may run it, the defaults, the models named."""
    return schemas.ProvidersResponse.of(await readiness.runnable_by(session, vault, actor.scope))


# Read off the plugin's constructor, so a console draws a form a plugin changes with its version.
@router.get("/v1/providers/{vendor}/options")
async def get_plugin_options(
    _actor: ProvidersKey, vendor: str, modality: Stage, builds: Annotated[str | None, Query()] = None
) -> schemas.PluginOptions:
    """What the vendor's plugin takes for a stage, beside the knobs the settings set: the arguments a form can draw."""
    return schemas.PluginOptions.of(plugin_options.form_of(modality, vendor, builds))


# `pinecall login` asks this once signed in: the host advises from what it serves and lends, and the
# org's own keys. The machine is its operator's to see.
@router.get("/v1/providers/advice")
async def advise(actor: ProvidersKey, vault: TheVault, session: Session) -> schemas.Advice:
    """What this host advises the org to run, stage by stage, and whose key each runs on."""
    operator = actor.person is not None and actor.person.operator
    return schemas.Advice.of(await advice.advise_for(session, vault, actor.scope, operator=operator))

"""The providers row read, written, seeded and checked: one JSON value of the box, edited from the console."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.enums import Stage
from runtime.exceptions import Conflict, ServiceUnavailable, ValidationError
from runtime.kit.db import VECTOR_WIDTH
from runtime.platform import service as platform
from runtime.providers.catalog import Catalog, StageChoice, StageOptions, read_stage_key
from runtime.providers.service.plugins import STAGES, class_path, models_listed, plugin, vendor_doing

UNSET = (
    "this box has no providers configuration yet: the operator writes it from the console, or "
    "`pinecall-runtime providers seed` writes the one it starts from"
)


def _dump(catalog: Catalog) -> dict[str, Any]:
    return catalog.model_dump(mode="json")


CATALOG: platform.Setting[Catalog] = platform.Setting("providers", Catalog.model_validate, _dump)


async def get_catalog(session: AsyncSession) -> Catalog:
    """The box's configuration; ServiceUnavailable until it was written."""
    catalog = await platform.find_setting(session, CATALOG)
    if catalog is None:
        raise ServiceUnavailable(UNSET)
    return catalog


async def put_catalog(session: AsyncSession, edited: Catalog) -> Catalog:
    """Write the configuration whole, as the console's box screen sends it; one naming what is not here is refused."""
    await platform.put_setting(session, CATALOG, check_catalog(edited))
    return edited


async def seed_catalog(session: AsyncSession, seeded: Catalog) -> None:
    """Write the configuration a box starts from; Conflict when one is already there."""
    if not await platform.put_setting_if_absent(session, CATALOG, check_catalog(seeded)):
        raise Conflict("this box is configured already: the console edits what is there")


def stage_options_of(catalog: Catalog, stage: Stage, vendor: str, model: str | None) -> StageOptions | None:
    """What a vendor is told for a stage and model: the row's word, on the class that runs that model."""
    options = catalog.options_for(stage, vendor, model)
    if options is None or options.builds is None or model is None or _its_class_runs(vendor, stage, options, model):
        return options
    return options.model_copy(update={"builds": None, "ends_the_turn": False})


# A class the row names (Deepgram's `STTv2`, the class Flux runs on) runs the models it lists by name; a model it
# does not list that the plugin's own class for the stage lists runs on that class, which ends no
# turn, as the row said the named class does. Listed by neither, the row's word stands. Deepgram's
# `nova-3` was built as `STTv2` and refused at the socket, so every call that named it never began
# (2026-11-05).
def _its_class_runs(vendor: str, stage: Stage, options: StageOptions, model: str) -> bool:
    module = plugin(vendor)
    listed = () if options.builds is None else models_listed(module, options.builds)
    if not listed or model in listed:
        return True
    own = class_path(module, stage)
    return own is None or model not in models_listed(module, own)


def judge_ceiling(catalog: Catalog) -> float | None:
    """What one call may spend on the box's judge, or None where the row names no judge."""
    return None if catalog.judge is None else catalog.judge.ceiling_usd


# A row that names a vendor nobody installed, or for a stage it does not do, is refused where it
# is written, not on the first call that reads it.
def check_catalog(written: Catalog) -> Catalog:
    """The configuration: each vendor installed and doing its stage, the embedder at 1024 wide."""
    for stage, choice in written.defaults.items():
        vendor_doing(choice.vendor, stage)
        for fallback in choice.fallbacks:
            _check_fallback(written, stage, choice, fallback)
    for key in written.models:
        _check_stage_key(key)
    for key, options in written.tuning.items():
        if _check_stage_key(key) is not Stage.llm and options.request:
            raise ValidationError(f"{key}: `request` is what a model is asked beside the conversation, so only llm")
    for vendor in written.tts_vendors_named():
        vendor_doing(vendor, Stage.tts)
    _check_harness(written)
    if written.embedding is not None and written.embedding.dimensions != VECTOR_WIDTH:
        raise ValidationError(
            f"the embedder answers {written.embedding.dimensions}-wide vectors; every vector "
            f"column is halfvec({VECTOR_WIDTH}), so it must be asked for {VECTOR_WIDTH}"
        )
    return written


# The models the harness asks on the box's keys: the judge's, alone, and the simulated caller's.
def _check_harness(written: Catalog) -> None:
    if written.caller is not None and written.caller.llm is not None:
        vendor_doing(written.caller.llm.vendor, Stage.llm)
    if written.judge is not None:
        vendor_doing(written.judge.llm.vendor, Stage.llm)
        if written.judge.llm.fallbacks:
            raise ValidationError("the judge runs on one model: fallbacks are for the stages of a call")


# `stt/deepgram`, or `llm/anthropic/claude-haiku-5-5` where the key names a model of the vendor.
def _check_stage_key(key: str) -> Stage:
    named, vendor = read_stage_key(key)
    if named not in STAGES:
        raise ValidationError(f"{key!r}: a stage is one of {', '.join(STAGES)}")
    stage = Stage(named)
    vendor_doing(vendor, stage)
    return stage


# The ears are chosen once for the whole session: a fallback that ends the turn itself where the
# primary does not (or the reverse) would leave the call with nobody ending the caller's turn.
def _check_fallback(written: Catalog, stage: Stage, primary: StageChoice, fallback: StageChoice) -> None:
    vendor_doing(fallback.vendor, stage)
    if fallback.fallbacks:
        raise ValidationError(f"{stage} fallback {fallback.vendor}: a fallback names no fallbacks of its own")
    if stage is not Stage.stt or _ends_the_turn(written, fallback) == _ends_the_turn(written, primary):
        return
    how = "ends the turn itself" if _ends_the_turn(written, fallback) else "leaves the turn open"
    raise ValidationError(
        f"stt fallback {fallback.vendor}: it {how} and {primary.vendor} does the other; the session reads "
        "the end of the turn one way for the whole call, so every vendor of the stage must end it alike"
    )


def _ends_the_turn(written: Catalog, choice: StageChoice) -> bool:
    options = stage_options_of(written, Stage.stt, choice.vendor, choice.model)
    return options is not None and options.ends_the_turn

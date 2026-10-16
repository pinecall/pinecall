"""The providers row: one JSON value in box_settings the operator edits from the console."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.agents.declaration import Modality
from pinecall_runtime.exceptions import Conflict, ServiceUnavailable, ValidationError
from pinecall_runtime.platform import service as platform
from pinecall_runtime.providers.schemas import VECTOR_WIDTH, Catalog, Stage, StageOptions
from pinecall_runtime.providers.service.plugins import MODALITIES, vendor_doing

ROW = "providers"

UNSET = (
    "this box has no providers configuration yet: the operator writes it from the console, or "
    "`pinecall-runtime providers seed` writes the one it starts from"
)


async def get_catalog(session: AsyncSession) -> Catalog:
    """The box's configuration; ServiceUnavailable until it was written."""
    value = await platform.get_setting(session, ROW)
    if value is None:
        raise ServiceUnavailable(UNSET)
    return Catalog.model_validate(value)


async def put_catalog(session: AsyncSession, edited: Catalog) -> None:
    """Write the configuration whole, as the console's box screen sends it."""
    check_catalog(edited)
    await platform.put_setting(session, ROW, edited.model_dump(mode="json"))


async def seed_catalog(session: AsyncSession, seeded: Catalog) -> None:
    """Write the configuration a box starts from; Conflict when one is already there."""
    check_catalog(seeded)
    if not await platform.put_setting_if_absent(session, ROW, seeded.model_dump(mode="json")):
        raise Conflict("this box is configured already: the console edits what is there")


def tuning_of(catalog: Catalog, modality: Modality, vendor: str, model: str | None) -> StageOptions | None:
    """What a vendor is told for a stage: the longest key naming the model's id, else its own."""
    stage = f"{modality}/{vendor}"
    models = (key.removeprefix(f"{stage}/") for key in catalog.tuning if key.startswith(f"{stage}/"))
    named = None if model is None else longest_prefix(models, model)
    return catalog.tuning.get(stage if named is None else f"{stage}/{named}")


def longest_prefix(keys: Iterable[str], name: str) -> str | None:
    """The longest of the keys the name starts with, so a dated snapshot reads as its family."""
    listed = [key for key in keys if name.startswith(key)]
    return max(listed, key=len) if listed else None


def judge_ceiling(catalog: Catalog) -> float | None:
    """What one call may spend on the box's judge, or None where the row names no judge."""
    return None if catalog.judge is None else catalog.judge.ceiling_usd


# A row that names a vendor nobody installed, or for a stage it does not do, is refused where it
# is written, not on the first call that reads it.
def check_catalog(written: Catalog) -> Catalog:
    """The configuration: each vendor installed and doing its stage, the embedder at 1024 wide."""
    for modality, stage in written.defaults.items():
        vendor_doing(stage.vendor, modality)
        for fallback in stage.fallbacks:
            _a_fallback(written, modality, stage, fallback)
    for key in written.models:
        _a_stage_key(key)
    for key, options in written.tuning.items():
        if _a_stage_key(key) != "llm" and options.request:
            raise ValidationError(f"{key}: `request` is what a model is asked beside the conversation, so only llm")
    for key in (*written.voices, *written.listed):
        vendor_doing(key.partition("/")[0], "tts")
    _harness_checked(written)
    if written.embedding is not None and written.embedding.dimensions != VECTOR_WIDTH:
        raise ValidationError(
            f"the embedder answers {written.embedding.dimensions}-wide vectors; every vector "
            f"column is halfvec({VECTOR_WIDTH}), so it must be asked for {VECTOR_WIDTH}"
        )
    return written


# The models the harness asks on the box's keys: the judge's, alone, and the simulated caller's.
def _harness_checked(written: Catalog) -> None:
    if written.caller is not None and written.caller.llm is not None:
        vendor_doing(written.caller.llm.vendor, "llm")
    if written.judge is not None:
        vendor_doing(written.judge.llm.vendor, "llm")
        if written.judge.llm.fallbacks:
            raise ValidationError("the judge runs on one model: fallbacks are for the stages of a call")


# `stt/deepgram`, or `llm/anthropic/claude-haiku-5-5` where the key names a model of the vendor.
def _a_stage_key(key: str) -> Modality:
    modality, _, vendor = key.partition("/")
    if modality not in MODALITIES:
        raise ValidationError(f"{key!r}: a stage is one of {', '.join(MODALITIES)}")
    vendor_doing(vendor.partition("/")[0], modality)
    return modality


# The ears are chosen once for the whole session: a fallback that ends the turn itself where the
# primary does not (or the reverse) would leave the call with nobody ending the caller's turn.
def _a_fallback(written: Catalog, modality: Modality, primary: Stage, fallback: Stage) -> None:
    vendor_doing(fallback.vendor, modality)
    if fallback.fallbacks:
        raise ValidationError(f"{modality} fallback {fallback.vendor}: a fallback names no fallbacks of its own")
    if modality != "stt" or _ends_the_turn(written, fallback) == _ends_the_turn(written, primary):
        return
    how = "ends the turn itself" if _ends_the_turn(written, fallback) else "leaves the turn open"
    raise ValidationError(
        f"stt fallback {fallback.vendor}: it {how} and {primary.vendor} does the other; the session reads "
        "the end of the turn one way for the whole call, so every vendor of the stage must end it alike"
    )


def _ends_the_turn(written: Catalog, stage: Stage) -> bool:
    options = tuning_of(written, "stt", stage.vendor, stage.model)
    return options is not None and options.ends_the_turn

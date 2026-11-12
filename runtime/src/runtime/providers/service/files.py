"""The files an operator applies to the row: a prices file and a models file, read from CSV, and what each changes."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass

from runtime.enums import Stage
from runtime.exceptions import ValidationError
from runtime.providers.catalog import Rate, model_key, stage_key

# A prices file's unit, and the field of `Rate` it fills.
FIELD_OF_UNIT = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cached_input_tokens": "cached_input",
    "cache_creation_tokens": "cache_creation",
    "characters": "characters",
    "audio_seconds": "audio_seconds",
    "minutes": "minutes",
}
PRICE_COLUMNS = ("vendor", "model", "unit", "usd", "as_of", "source")
MODEL_COLUMNS = ("vendor", "stage", "model", "name", "as_of", "source")
# A seventh column a models file may carry: `yes` on the models a picker leads with for a voice agent.
RECOMMENDED = "recommended"
YES = frozenset({"yes", "y", "true", "1"})
# The stages a models file may name, in the order a call runs them.
STAGES: tuple[Stage, ...] = tuple(Stage)


@dataclass(frozen=True)
class ModelsFile:
    """A models file read: what a picker offers by `stage/vendor`, each model's name, and the ones it leads with."""

    offered: dict[str, tuple[str, ...]]
    # `vendor/model`: the name the vendor gives it, where it is not the id.
    names: dict[str, str]
    # `stage/vendor`: the models marked recommended, in the file's order.
    recommended: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Change:
    """What writing a file would do to what the box holds, key by key: a model's rate, a stage and vendor's models."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    # Kept as they are: a file adds and replaces, it never removes.
    only_on_the_box: tuple[str, ...]


def change_of[T](box: Mapping[str, T], written: Mapping[str, T]) -> Change:
    """Each key of the file as new, changed or the same, and what only the box holds."""
    return Change(
        added=tuple(sorted(key for key in written if key not in box)),
        changed=tuple(sorted(key for key in written if key in box and box[key] != written[key])),
        unchanged=tuple(sorted(key for key in written if key in box and box[key] == written[key])),
        only_on_the_box=tuple(sorted(key for key in box if key not in written)),
    )


def rates_from_csv(text: str) -> dict[str, Rate]:
    """The rates of a prices file, one row per model and unit; `#` lines are notes."""
    reader = csv.DictReader(_lines_of(text))
    if tuple(reader.fieldnames or ()) != PRICE_COLUMNS:
        raise ValidationError(f"a prices file has the columns {','.join(PRICE_COLUMNS)}")
    fields: dict[str, dict[str, float | str]] = {}
    vendors: dict[str, str] = {}
    for number, row in enumerate(reader, start=2):
        model, unit = row["model"], row["unit"]
        field = FIELD_OF_UNIT.get(unit)
        if field is None:
            raise ValidationError(f"line {number}: {unit!r} is not a unit; one of {', '.join(FIELD_OF_UNIT)}")
        if vendors.setdefault(model, row["vendor"]) != row["vendor"]:
            raise ValidationError(f"line {number}: {model} is {vendors[model]}'s already: a model is priced once")
        priced = fields.setdefault(model, {"as_of": ""})
        if field in priced:
            raise ValidationError(f"line {number}: {model} {unit} is priced twice")
        priced[field] = _read_usd(row["usd"], number)
        priced["as_of"] = max(str(priced["as_of"]), row["as_of"])
    return {model: Rate.model_validate(priced) for model, priced in fields.items()}


def models_from_csv(text: str) -> ModelsFile:
    """The models of a models file, by `stage/vendor`, in the file's order; `#` lines are notes."""
    reader = csv.DictReader(_lines_of(text))
    if tuple(reader.fieldnames or ()) not in (MODEL_COLUMNS, (*MODEL_COLUMNS, RECOMMENDED)):
        raise ValidationError(
            f"a models file has the columns {','.join(MODEL_COLUMNS)}, and {RECOMMENDED} after them or not"
        )
    offered: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    recommended: dict[str, list[str]] = {}
    for number, row in enumerate(reader, start=2):
        stage, vendor, model = row["stage"], row["vendor"], row["model"]
        if stage not in STAGES:
            raise ValidationError(f"line {number}: {stage!r} is not a stage; one of {', '.join(STAGES)}")
        if not vendor or not model:
            raise ValidationError(f"line {number}: a row names its vendor and its model")
        named = stage_key(stage, vendor)
        listed = offered.setdefault(named, [])
        if model in listed:
            raise ValidationError(f"line {number}: {vendor}/{model} is listed twice for {stage}")
        listed.append(model)
        if row["name"] and row["name"] != model:
            names[model_key(vendor, model)] = row["name"]
        if (row.get(RECOMMENDED) or "").strip().lower() in YES:
            recommended.setdefault(named, []).append(model)
    return ModelsFile(
        offered={named: tuple(models) for named, models in offered.items()},
        names=names,
        recommended={named: tuple(models) for named, models in recommended.items()},
    )


def _lines_of(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("#")]


def _read_usd(text: str, number: int) -> float:
    try:
        usd = float(text)
    except ValueError:
        raise ValidationError(f"line {number}: {text!r} is not a price in dollars") from None
    if usd < 0:
        raise ValidationError(f"line {number}: a price is never below zero")
    return usd

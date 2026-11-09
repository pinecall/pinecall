"""The models file an operator applies: what a picker offers of each vendor, by stage, read from a CSV and diffed."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass

from pinecall_runtime.exceptions import ValidationError

COLUMNS = ("vendor", "stage", "model", "name", "as_of", "source")
# A seventh column a file may carry: `yes` on the models a picker leads with for a voice agent.
RECOMMENDED = "recommended"
YES = frozenset({"yes", "y", "true", "1"})
STAGES = ("stt", "llm", "tts")


@dataclass(frozen=True)
class ModelsFile:
    """A models file read: what a picker offers by `stage/vendor`, each model's name, and the ones it leads with."""

    offered: dict[str, tuple[str, ...]]
    # `vendor/model`: the name the vendor gives it, where it is not the id.
    names: dict[str, str]
    # `stage/vendor`: the models marked recommended, in the file's order.
    recommended: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class OfferedChange:
    """Each `stage/vendor` of the file as new, changed or the same, and what only the box offers."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    only_on_the_box: tuple[str, ...]


def models_from_csv(text: str) -> ModelsFile:
    """The models of a models file, by `stage/vendor`, in the file's order; `#` lines are notes."""
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    reader = csv.DictReader(lines)
    if tuple(reader.fieldnames or ()) not in (COLUMNS, (*COLUMNS, RECOMMENDED)):
        raise ValidationError(f"a models file has the columns {','.join(COLUMNS)}, and {RECOMMENDED} after them or not")
    offered: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    recommended: dict[str, list[str]] = {}
    for number, row in enumerate(reader, start=2):
        stage, vendor, model = row["stage"], row["vendor"], row["model"]
        if stage not in STAGES:
            raise ValidationError(f"line {number}: {stage!r} is not a stage; one of {', '.join(STAGES)}")
        if not vendor or not model:
            raise ValidationError(f"line {number}: a row names its vendor and its model")
        named = f"{stage}/{vendor}"
        listed = offered.setdefault(named, [])
        if model in listed:
            raise ValidationError(f"line {number}: {vendor}/{model} is listed twice for {stage}")
        listed.append(model)
        if row["name"] and row["name"] != model:
            names[f"{vendor}/{model}"] = row["name"]
        if (row.get(RECOMMENDED) or "").strip().lower() in YES:
            recommended.setdefault(named, []).append(model)
    return ModelsFile(
        offered={named: tuple(models) for named, models in offered.items()},
        names=names,
        recommended={named: tuple(models) for named, models in recommended.items()},
    )


def offered_changed(box: Mapping[str, tuple[str, ...]], written: Mapping[str, tuple[str, ...]]) -> OfferedChange:
    """Each stage and vendor of the file as new, changed or the same, and what only the box holds."""
    return OfferedChange(
        added=tuple(sorted(named for named in written if named not in box)),
        changed=tuple(sorted(named for named in written if named in box and box[named] != written[named])),
        unchanged=tuple(sorted(named for named in written if box.get(named) == written[named])),
        only_on_the_box=tuple(sorted(named for named in box if named not in written)),
    )

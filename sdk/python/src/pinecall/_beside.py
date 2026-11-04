"""The folder beside a class: where its file is, for what a class ships from next to itself."""

import inspect
from pathlib import Path


def folder_of(cls: type) -> Path | None:
    """The folder the class's file is in; None for a class with no file."""
    try:
        return Path(inspect.getfile(cls)).resolve().parent
    except (TypeError, OSError):
        return None

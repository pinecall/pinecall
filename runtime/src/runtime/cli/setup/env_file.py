"""The installation's settings file: `NAME=value` lines, owner-only, written by one object."""

import os
from pathlib import Path

from runtime.config import Settings


# Until 2026-11 three functions in three modules wrote this file, each its own way.
class EnvFile:
    """The installation's settings file: read whole, changed name by name, read as the runtime's settings."""

    def __init__(self, path: Path) -> None:
        """The file at this path, which may not be there yet."""
        self.path = path

    def exists(self) -> bool:
        """Whether a run before this one wrote it."""
        return self.path.is_file()

    def read(self) -> dict[str, str]:
        """The file as `NAME=value` pairs; nothing for a file not written yet."""
        if not self.path.is_file():
            return {}
        pairs = (line.partition("=") for line in self.path.read_text(encoding="utf-8").splitlines())
        return {name: value for name, _, value in pairs if name and not name.startswith("#")}

    def create(self, text: str) -> None:
        """Write the file the first time, owner-only."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600)
        self.path.write_text(text, encoding="utf-8")

    def set(self, **changes: str | None) -> dict[str, str]:
        """Those names set (None takes one out), every other line kept; the pairs the file holds now."""
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.is_file() else []
        kept = [line for line in lines if line.partition("=")[0] not in changes]
        kept += [f"{name}={value}" for name, value in changes.items() if value is not None]
        self.path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return self.read()

    def settings(self) -> Settings:
        """The runtime's settings from the file, over the process's own environment."""
        return settings_of(self.read())


def settings_of(values: dict[str, str]) -> Settings:
    """The runtime's settings from those pairs, over the process's own environment."""
    variables = {**os.environ, **values}
    return Settings.model_validate(variables)

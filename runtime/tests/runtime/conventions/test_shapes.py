"""Shapes at home: pydantic is imported by the wire and the bodies, and by nothing else that is not named here."""

from tests.runtime.conventions.canon import Module

# Where pydantic is imported outside `wire/` and a `schemas` module, each for one reason. A vendor's
# client that parses that vendor's answers keeps its shapes beside it, and is named here when it is built.
ALLOWED: dict[str, str] = {
    "config": "the settings are read with pydantic-settings",
    "kit.schemas": "the bases every body is built on",
}


def test_pydantic_lives_in_the_wire_and_the_bodies(modules: dict[str, Module]) -> None:
    """A module that imports pydantic is in `wire/`, is a `schemas` module, or is named with its reason."""
    wrong: list[str] = []
    for module in modules.values():
        if module.parts[0] == "wire" or "schemas" in module.parts or module.name in ALLOWED:
            continue
        for target, _names, line in module.imports():
            if target.split(".")[0] in ("pydantic", "pydantic_settings"):
                wrong.append(f"{module.shown}:{line}: imports {target} outside the wire and the bodies")
    assert not wrong, "\n".join(wrong)

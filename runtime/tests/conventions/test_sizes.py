"""Rule 9 and rule 12: the sizes a module keeps to, and the one-line docstring that opens it."""

import ast

from tests.conventions.canon import ENTRYPOINTS, Module

MOST_LINES = 500
MOST_LINES_OF_SHAPES = 800
MOST_LINES_OF_AN_ENTRYPOINT = 300


def test_modules_keep_to_their_size(modules: dict[str, Module]) -> None:
    """A module is at most 500 lines, a module of shapes 800, an entrypoint 300."""
    wrong: list[str] = []
    for module in modules.values():
        lines = module.path.read_text(encoding="utf-8").count("\n")
        most = _most_lines_of(module)
        if lines > most:
            wrong.append(f"{module.shown}: {lines} lines, over {most}")
    assert not wrong, "\n".join(wrong)


def test_every_module_opens_with_a_one_line_docstring(modules: dict[str, Module]) -> None:
    """The first statement of a module is a docstring of one line saying what the module is."""
    wrong: list[str] = []
    for module in modules.values():
        if module.name.startswith("migrations.versions"):
            continue
        doc = ast.get_docstring(module.tree, clean=False)
        if doc is None:
            wrong.append(f"{module.shown}: no docstring")
        elif "\n" in doc.strip():
            wrong.append(f"{module.shown}: the docstring runs over one line")
    assert not wrong, "\n".join(wrong)


def _most_lines_of(module: Module) -> int:
    if module.parts[0] in ENTRYPOINTS:
        return MOST_LINES_OF_AN_ENTRYPOINT
    if module.parts[0] == "wire" or module.kind == "schemas" or module.parts[-1] == "schemas":
        return MOST_LINES_OF_SHAPES
    return MOST_LINES

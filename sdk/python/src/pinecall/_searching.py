"""Whether a class searches its knowledge bases, read off its own file with `ast`."""

import ast
import inspect

# `self.knowledge.search(…)`, `knowledge.search(…)`, `self.call.search(…)`, `call.search(…)`.
SEARCHED_THROUGH = frozenset({"knowledge", "call"})


def searches(cls: type) -> bool:
    """Whether the class's file calls a search; sent as `uses_knowledge` when it registers.

    A world with no base attached is then refused when the agent registers, not at the first turn.
    """
    try:
        source = inspect.getsource(inspect.getmodule(cls) or cls)
    except (OSError, TypeError):
        return False
    return in_source(source)


def in_source(source: str) -> bool:
    """Whether the source calls `.search` on a knowledge or a call; a word in a string does not."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "search":
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id in SEARCHED_THROUGH:
            return True
        if isinstance(owner, ast.Attribute) and owner.attr in SEARCHED_THROUGH:
            return True
    return False

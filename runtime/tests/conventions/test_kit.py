"""The toolkit is generic: it imports nothing of ours above itself, and a web framework in its web modules alone."""

from tests.conventions.canon import Module, of_ours

# The modules of `kit/` that are about HTTP, and so may import the framework.
WEB = frozenset({"middleware", "sse", "websockets", "http"})
FRAMEWORKS = frozenset({"fastapi", "starlette"})
# What `kit/` may read of the package: itself and the words every table and shape share.
BELOW = frozenset({"kit", "enums", "exceptions"})


def test_kit_imports_nothing_above_itself(modules: dict[str, Module]) -> None:
    """A module of `kit/` imports `kit`, `enums` and `exceptions`, nothing else of ours."""
    wrong: list[str] = []
    for module in modules.values():
        if module.parts[0] != "kit":
            continue
        for target, _names, line in module.imports():
            head, dotted = of_ours(target)
            if head is not None and head not in BELOW:
                wrong.append(f"{module.shown}:{line}: kit imports {dotted}")
            if target.split(".")[0] in FRAMEWORKS and module.kind not in WEB:
                wrong.append(f"{module.shown}:{line}: {target} outside kit's web modules")
    assert not wrong, "\n".join(wrong)

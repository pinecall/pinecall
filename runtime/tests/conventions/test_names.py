"""The names: no banned word in an identifier, a module alias resolves, and a function is named by a verb."""

import ast

from tests.conventions.canon import PACKAGE, Module

# The vocabulary's `never` column (CONTRIBUTING.md), as whole words of an identifier.
BANNED = frozenset(
    {"door", "doors", "world", "worlds", "corner", "bearer", "acting", "knock", "knocks", "letter", "letters"}
    | {"tuning", "knob", "knobs", "declared", "declarations"}
)
# Identifiers that carry a banned word on purpose, and why; each goes when its reason does. An identifier is
# named whole: `tuning` the field is kept, `tuning_of` a function is not.
ALLOWED: dict[str, str] = {
    # The console and the SDKs read `world` off the wire; the field follows them when they move to `env`.
    "world": "a wire field the console still reads",
    # The providers row is a document the box keeps, and the release before 2026-11 reads this key of it.
    "tuning": "a key of the stored providers row, read by the release that runs beside this one",
}


def test_no_banned_word_in_an_identifier(modules: dict[str, Module]) -> None:
    """No name, argument, function, class or attribute is one of the banned words."""
    wrong: list[str] = []
    for module in modules.values():
        for node in ast.walk(module.tree):
            for name, line in _identifiers(node):
                for word in name.lower().split("_"):
                    if word in BANNED and name not in ALLOWED:
                        wrong.append(f"{module.shown}:{line}: `{name}` says {word}")
    assert not wrong, "\n".join(wrong)


def test_every_module_alias_resolves(modules: dict[str, Module]) -> None:
    """`alias.attr`, where alias is a module of ours, names something the module defines."""
    wrong: list[str] = []
    defined: dict[str, set[str]] = {}
    for module in modules.values():
        aliases = _aliases(modules, module)
        if not aliases:
            continue
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                target = aliases[node.value.id]
                if target not in defined:
                    defined[target] = _defined(modules, target)
                if node.attr not in defined[target]:
                    wrong.append(
                        f"{module.shown}:{node.lineno}: {node.value.id}.{node.attr}: no `{node.attr}` in {target}"
                    )
    assert not wrong, "\n".join(wrong)


def _identifiers(node: ast.AST) -> list[tuple[str, int]]:
    match node:
        case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
            return [(node.name, node.lineno)]
        case ast.arg():
            return [(node.arg, node.lineno)]
        case ast.Name(ctx=ast.Store()):
            return [(node.id, node.lineno)]
        case ast.Attribute(ctx=ast.Store()):
            return [(node.attr, node.lineno)]
        case ast.alias(asname=str() as asname):
            return [(asname, node.lineno)]
        case _:
            return []


def _aliases(modules: dict[str, Module], module: Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in module.tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(PACKAGE + ".")
            and node.level == 0
        ):
            for alias in node.names:
                full = f"{node.module}.{alias.name}"[len(PACKAGE) + 1 :]
                if full in modules:
                    aliases[alias.asname or alias.name] = full
        elif isinstance(node, ast.Import):
            for alias in node.names:
                full = alias.name[len(PACKAGE) + 1 :] if alias.name.startswith(PACKAGE + ".") else ""
                if full and alias.asname and full in modules:
                    aliases[alias.asname] = full
    return aliases


def _defined(modules: dict[str, Module], name: str) -> set[str]:
    out: set[str] = set()
    for node in modules[name].tree.body:
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                out.add(node.name)
            case ast.Assign():
                out.update(target.id for target in ast.walk(node) if isinstance(target, ast.Name))
            case ast.AnnAssign(target=ast.Name() as target):
                out.add(target.id)
            case ast.TypeAlias(name=ast.Name() as alias):
                out.add(alias.id)
            case ast.Import() | ast.ImportFrom():
                out.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
            case _:
                pass
    depth = name.count(".") + 1
    out.update(
        other.rsplit(".", 1)[1] for other in modules if other.startswith(name + ".") and other.count(".") == depth
    )
    return out


# A function says what it does: `list_calls`, never `listed`. The irregular participles the old tree used,
# and the regular ones by their ending; a verb that ends the same way is named here.
PARTICIPLES = frozenset(
    {"kept", "said", "heard", "sent", "taken", "given", "written", "known", "seen", "done", "gone", "made", "held"}
    | {"told", "left", "lost", "spent", "shown", "drawn", "chosen", "forgotten", "begun", "brought", "bought", "paid"}
)
VERBS_IN_ED = frozenset({"embed", "need", "feed", "seed", "speed", "proceed", "exceed", "shed", "succeed", "bleed"})


def test_a_function_is_named_by_a_verb(modules: dict[str, Module]) -> None:
    """No function or method opens with a past participle; a property may be an adjective."""
    wrong: list[str] = []
    for module in modules.values():
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or _is_a_property(node):
                continue
            first = node.name.strip("_").split("_")[0]
            if first in PARTICIPLES or (first.endswith("ed") and first not in VERBS_IN_ED):
                wrong.append(f"{module.shown}:{node.lineno}: `{node.name}` is named by a participle, not a verb")
    assert not wrong, "\n".join(wrong)


def _is_a_property(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    names = {ast.unparse(decorator).split(".")[-1].split("(")[0] for decorator in node.decorator_list}
    return bool(names & {"property", "cached_property", "setter", "fixture"})

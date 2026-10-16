"""Rule 2, the layers: no module cycles, no import upwards, and each file of a domain in its place."""

import ast
import sys
from collections import defaultdict

from tests.conventions.canon import DOMAINS, ENTRYPOINTS, FOUNDATIONS, VALUE_OBJECTS, Module, of_ours


def test_no_module_cycles(modules: dict[str, Module]) -> None:
    """The module graph, as imports run at import time, has no cycle."""
    cycles = _strongly_connected(_edges(modules))
    shown = ["\n  " + " → ".join(sorted(component)) for component in cycles]
    assert not cycles, f"modules that import each other, round:{''.join(shown)}"


def test_domains_import_downwards(modules: dict[str, Module]) -> None:
    """A domain's module reaches a lower domain's service, its schemas or a value object; never upwards."""
    wrong: list[str] = []
    for module in modules.values():
        domain = module.domain
        if domain is None or module.kind in ("endpoints", "auth"):
            continue
        for target, names, line in module.imports():
            head, dotted = of_ours(target)
            if head is None or head in FOUNDATIONS or head == domain:
                continue
            where = f"{module.shown}:{line}"
            if _a_value_object(dotted, names):
                continue
            if head in ENTRYPOINTS or head not in DOMAINS:
                wrong.append(f"{where}: a domain never imports {dotted}")
            elif DOMAINS.index(head) > DOMAINS.index(domain):
                wrong.append(f"{where}: {domain} imports {dotted}, which is above it")
            else:
                wrong.extend(f"{where}: {why}" for why in _downward_refusals(modules, module, dotted, names))
    assert not wrong, "\n".join(wrong)


def test_endpoints_stay_at_the_top(modules: dict[str, Module]) -> None:
    """Endpoints call services and read schemas; never a repository, a model, SQLAlchemy or another's endpoints."""
    wrong: list[str] = []
    for module in modules.values():
        if module.domain is None or module.kind != "endpoints":
            continue
        for target, names, line in module.imports():
            where = f"{module.shown}:{line}"
            if target.split(".")[0] == "sqlalchemy":
                wrong.append(f"{where}: endpoints never import SQLAlchemy ({target})")
            head, dotted = of_ours(target)
            if head is None:
                continue
            if head in DOMAINS and (dotted.split(".")[1:2] == ["models"] or (dotted == head and "models" in names)):
                wrong.append(f"{where}: endpoints never import a model ({dotted} {names})")
            if head in DOMAINS and (".repository" in dotted or (dotted == head and "repository" in names)):
                wrong.append(f"{where}: endpoints never import a repository ({dotted})")
            if head in DOMAINS and head != module.domain and (".endpoints" in dotted or "endpoints" in names):
                wrong.append(f"{where}: no endpoints module imports another ({dotted})")
    assert not wrong, "\n".join(wrong)


def test_repositories_and_services_know_no_web(modules: dict[str, Module]) -> None:
    """A repository never imports a service or FastAPI; a service never imports FastAPI."""
    wrong: list[str] = []
    for module in modules.values():
        if module.domain is None or module.kind not in ("repository", "service"):
            continue
        for target, names, line in module.imports():
            where = f"{module.shown}:{line}"
            if target.split(".")[0] == "fastapi":
                wrong.append(f"{where}: a {module.kind} never imports FastAPI")
            head, dotted = of_ours(target)
            if module.kind == "repository" and head == module.domain and (".service" in dotted or "service" in names):
                wrong.append(f"{where}: a repository never imports its service")
    assert not wrong, "\n".join(wrong)


def test_only_api_imports_endpoints(modules: dict[str, Module]) -> None:
    """The endpoints are mounted by `api.py` and reached by nothing else."""
    wrong: list[str] = []
    for module in modules.values():
        if module.name == "api" or (module.domain is not None and module.kind == "endpoints"):
            continue
        for target, names, line in module.imports():
            head, dotted = of_ours(target)
            if head in DOMAINS and (".endpoints" in dotted or (dotted == head and "endpoints" in names)):
                wrong.append(f"{module.shown}:{line}: imports {dotted}")
    assert not wrong, "\n".join(wrong)


# A lower domain is reached as a module: its service package, a module of that package, its
# models (a table is read as a table), its schemas (from a schemas module), or one of the two value
# objects. A name out of a service is not imported: the call site then says which domain answers
# (`billing.get_quotas`).
def _downward_refusals(modules: dict[str, Module], module: Module, dotted: str, names: list[str]) -> list[str]:
    imported = [f"{dotted}.{name}" for name in names]
    if all(each in modules for each in imported):
        kinds = {each.split(".")[1] for each in imported}
        if kinds <= {"service", "models"} or (kinds <= {"schemas"} and module.kind == "schemas"):
            return []
        return [f"{dotted} {names}: a lower domain is reached through its service"]
    second = dotted.split(".")[1:2]
    if second == ["models"] or (dotted in DOMAINS and names == ["models"]):
        return []
    if second == ["schemas"] and module.kind == "schemas":
        return []
    if second == ["service"]:
        return [f"{dotted} {names}: a name out of a lower service; import the module and qualify the name"]
    return [f"{dotted} {names}: a lower domain is reached through its service or, from a schemas module, its schemas"]


# What runs at import: module-level imports, each resolved to the module it lands in. Importing
# `a.b.c` also runs `a/__init__` and `a/b/__init__`; a package of the module's own is already
# running when the module is, so that edge is not a cycle.
def _edges(modules: dict[str, Module]) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for module in modules.values():
        for node in module.tree.body:
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                targets = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            for target in targets:
                head, dotted = of_ours(target)
                if head is None:
                    continue
                resolved = _resolve(modules, dotted)
                if resolved and resolved != module.name and not module.name.startswith(resolved + "."):
                    edges[module.name].add(resolved)
                parts = dotted.split(".")
                for i in range(1, len(parts)):
                    package = ".".join(parts[:i])
                    if package in modules and package != module.name and not module.name.startswith(package + "."):
                        edges[module.name].add(package)
    return edges


# `from pinecall_runtime.calls.context import Route`, or `from pinecall_runtime.calls import context`.
def _a_value_object(dotted: str, names: list[str]) -> bool:
    return dotted in VALUE_OBJECTS or (dotted in DOMAINS and all(f"{dotted}.{name}" in VALUE_OBJECTS for name in names))


def _resolve(modules: dict[str, Module], dotted: str) -> str | None:
    while dotted and dotted not in modules:
        dotted = dotted.rsplit(".", 1)[0] if "." in dotted else ""
    return dotted or None


def _strongly_connected(edges: dict[str, set[str]]) -> list[list[str]]:
    sys.setrecursionlimit(10_000)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []
    counter = 0

    def strong(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for other in edges.get(node, ()):
            if other not in index:
                strong(other)
                low[node] = min(low[node], low[other])
            elif other in on_stack:
                low[node] = min(low[node], index[other])
        if low[node] == index[node]:
            component: list[str] = []
            while True:
                popped = stack.pop()
                on_stack.discard(popped)
                component.append(popped)
                if popped == node:
                    break
            if len(component) > 1:
                found.append(component)

    for node in list(edges):
        if node not in index:
            strong(node)
    return found


def test_models_declare_and_import_nothing_of_ours_but_the_base(modules: dict[str, Module]) -> None:
    """A domain's models import `kit.db` and `enums`, nothing else of ours: they declare, they never query."""
    wrong: list[str] = []
    for module in modules.values():
        if module.domain is None or module.kind != "models":
            continue
        for target, _names, line in module.imports():
            head, dotted = of_ours(target)
            if head is None:
                continue
            if dotted not in ("kit.db", "enums") and not dotted.startswith(f"{module.domain}.models"):
                wrong.append(f"{module.shown}:{line}: a models module imports {dotted}")
    assert not wrong, "\n".join(wrong)


def test_alembic_sees_every_domains_tables(modules: dict[str, Module]) -> None:
    """`migrations/env.py` imports the models of every domain that has any, so the metadata is whole."""
    env = modules["migrations.env"]
    imported: set[str] = set()
    for target, names, _line in env.imports():
        _head, dotted = of_ours(target)
        if dotted:
            imported.update([dotted, *(f"{dotted}.{name}" for name in names)])
    missing = sorted(
        f"{domain}.models" for domain in DOMAINS if f"{domain}.models" in modules and f"{domain}.models" not in imported
    )
    assert not missing, f"env.py does not import {missing}"

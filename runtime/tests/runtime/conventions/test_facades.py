"""A facade is a contract: a service package exports what another domain imports, and nothing else."""

import ast

from tests.runtime.conventions.canon import DOMAINS, SRC, Module, of_ours


def test_a_service_package_exports_what_others_use(modules: dict[str, Module]) -> None:
    """Every name in a `service/__init__.py`'s `__all__` is used by a module outside the domain."""
    wrong: list[str] = []
    used = _used_from_outside(modules)
    for domain in DOMAINS:
        name = f"{domain}.service"
        if name not in modules or not (SRC / domain / "service").is_dir():
            continue
        for exported in _exported(modules[name]):
            if exported not in used.get(domain, set()):
                wrong.append(f"{domain}/service/__init__.py: exports `{exported}`, which nothing outside {domain} uses")
    assert not wrong, "\n".join(wrong)


def _exported(module: Module) -> list[str]:
    for node in module.tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            return [e.value for e in ast.walk(node.value) if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


# `from runtime.billing import service as billing` then `billing.get_quotas`: the attribute is the use.
def _used_from_outside(modules: dict[str, Module]) -> dict[str, set[str]]:
    used: dict[str, set[str]] = {}
    for module in modules.values():
        aliases: dict[str, str] = {}
        for target, names, _line in module.imports():
            head, dotted = of_ours(target)
            if head not in DOMAINS or head == module.domain:
                continue
            if dotted == f"{head}.service":
                used.setdefault(head, set()).update(names)
        for node in module.tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                head, dotted = of_ours(node.module)
                if head in DOMAINS and head != module.domain and dotted == head:
                    for alias in node.names:
                        if alias.name == "service":
                            aliases[alias.asname or alias.name] = head
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                used.setdefault(aliases[node.value.id], set()).add(node.attr)
    return used

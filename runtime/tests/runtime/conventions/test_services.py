"""A service speaks in values and owns no loop: it never imports its domain's schemas, nor they it."""

import ast

from tests.runtime.conventions.canon import Module, of_ours


def test_a_service_and_its_schemas_never_meet(modules: dict[str, Module]) -> None:
    """A `service` module imports no `schemas` of its domain, and a `schemas` module no `service` of its own."""
    wrong: list[str] = []
    for module in modules.values():
        if module.domain is None or module.kind not in ("service", "schemas"):
            continue
        other = "schemas" if module.kind == "service" else "service"
        for target, names, line in module.imports():
            head, dotted = of_ours(target)
            if head != module.domain:
                continue
            if dotted.split(".")[1:2] == [other] or (dotted == head and other in names):
                wrong.append(f"{module.shown}:{line}: a {module.kind} imports its domain's {other}")
    assert not wrong, "\n".join(wrong)


def test_a_loop_lives_in_tasks(modules: dict[str, Module]) -> None:
    """`while True` in a service is a loop without an owner, unless the function is a bounded `wait_for_…`."""
    wrong: list[str] = []
    for module in modules.values():
        if module.domain is None or module.kind != "service":
            continue
        for function in ast.walk(module.tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if function.name.startswith("wait_for_"):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
                    wrong.append(f"{module.shown}:{node.lineno}: `while True` in `{function.name}`: a loop is a task")
    assert not wrong, "\n".join(wrong)

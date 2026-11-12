"""An endpoint is transport: a short body, no process state read by hand, no box-wide session opened in it."""

import ast

from tests.conventions.canon import Module

MOST_STATEMENT_LINES = 15
ROUTE_VERBS = frozenset({"get", "post", "put", "patch", "delete"})


def test_a_route_body_is_short(modules: dict[str, Module]) -> None:
    """An HTTP route is its dependencies, one service call and a schema: fifteen lines of statements at most."""
    wrong: list[str] = []
    for module in _endpoints(modules):
        for node in ast.walk(module.tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_a_route(node):
                lines = _statement_lines(node)
                if lines > MOST_STATEMENT_LINES:
                    wrong.append(f"{module.shown}:{node.lineno}: `{node.name}` runs {lines} lines: a use case")
    assert not wrong, "\n".join(wrong)


def test_process_state_is_read_in_getters_alone(modules: dict[str, Module]) -> None:
    """`.state` is read where a getter is declared (an `auth` module, `handles.py`), in `app.py` and `lifespan.py`."""
    wrong: list[str] = []
    for module in modules.values():
        if module.kind == "auth" or module.parts[0] in ("handles", "app", "lifespan", "auth"):
            continue
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and node.attr == "state" and _is_a_request(node.value):
                wrong.append(f"{module.shown}:{node.lineno}: reads `.state` by hand: ask for the object by its getter")
    assert not wrong, "\n".join(wrong)


def test_an_endpoint_asks_for_its_session(modules: dict[str, Module]) -> None:
    """An endpoint never opens the box-wide scope itself: it asks for a `BoxSession` in its signature."""
    wrong: list[str] = []
    for module in _endpoints(modules):
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Name) and node.id == "box_wide":
                wrong.append(f"{module.shown}:{node.lineno}: opens `box_wide` in an endpoint")
    assert not wrong, "\n".join(wrong)


def _endpoints(modules: dict[str, Module]) -> list[Module]:
    return [module for module in modules.values() if module.domain is not None and module.kind == "endpoints"]


def _is_a_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in ROUTE_VERBS:
            return True
    return False


# The lines its statements span, the docstring left out: what a reader has to follow.
def _statement_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    body = node.body[1:] if ast.get_docstring(node) is not None else node.body
    if not body:
        return 0
    return (body[-1].end_lineno or body[-1].lineno) - body[0].lineno + 1


def _is_a_request(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "app"
    return isinstance(node, ast.Name) and node.id in ("request", "websocket", "app", "scope")

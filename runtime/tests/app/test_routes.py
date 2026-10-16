"""Every route reads its query as FastAPI parses it: a query model alone, so its fields are the parameters."""

from fastapi.routing import APIRoute, APIWebSocketRoute
from pydantic import BaseModel
from starlette.routing import BaseRoute

from pinecall_runtime.app import create_app


def _routes(routes: list[BaseRoute]) -> list[APIRoute | APIWebSocketRoute]:
    """Every endpoint, the included routers walked down."""
    found: list[APIRoute | APIWebSocketRoute] = []
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            found.extend(_routes(included.routes))
        elif isinstance(route, APIRoute | APIWebSocketRoute):
            found.append(route)
    return found


# Beside another query parameter FastAPI no longer reads a model flat: it asks for one parameter named
# after the argument, and every client's request is refused with 422.
def test_a_query_model_is_its_endpoints_only_query_parameter() -> None:
    """No endpoint takes a query model and another query parameter beside it."""
    wrong: list[str] = []
    for route in _routes(create_app().routes):
        query = route.dependant.query_params
        models = [
            p.name
            for p in query
            if isinstance(p.field_info.annotation, type) and issubclass(p.field_info.annotation, BaseModel)
        ]
        if models and len(query) > 1:
            wrong.append(f"{route.path}: {', '.join(p.name for p in query)}")
    assert not wrong, "\n".join(wrong)

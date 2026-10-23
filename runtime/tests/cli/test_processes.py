"""The processes: what the gateway serves with."""

import inspect
import io

import pytest
import typer
from livekit.agents.utils import http_context
from typer.core import TyperCommand

from pinecall_runtime.cli import processes
from pinecall_runtime.cli.command import OK, Context
from pinecall_runtime.cli.output import Printer
from pinecall_runtime.config import load_settings


async def test_the_gateway_serves_with_livekits_http_session_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plugin that asks LiveKit for its http session outside a job finds one in every request."""
    found: list[bool] = []

    async def serve(_server: processes.Stopping) -> None:
        found.append(not http_context.http_session().closed)

    monkeypatch.setattr(processes.Stopping, "serve", serve)
    monkeypatch.setattr(processes.providers, "installed", lambda: ())
    settings = load_settings().model_copy(update={"gateway_listen": "127.0.0.1:0"})
    printer = Printer(as_json=False, out=io.StringIO(), err=io.StringIO())
    ctx = typer.Context(TyperCommand("gateway"), obj=Context(settings, printer))
    assert await inspect.unwrap(processes.gateway)(ctx) == OK
    assert found == [True]

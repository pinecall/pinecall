"""`serve start` on a gateway: the registration first, the console's verbs, the ways to leave."""

import asyncio
import io
import json
from pathlib import Path

import pytest

from pinecall.serve._loading import CannotServe, parse
from pinecall.serve._starting import NO_DOOR, SIGNALLED, STOPPED, client_from, start
from tests.fakes.gateway import KEY, FakeGateway
from tests.fakes.project import written


def flags_of(tmp_path: Path, *more: str) -> list[str]:
    return ["--file", str(written(tmp_path)), "--slug", "recepcion", "--events", *more]


async def started(
    gateway: FakeGateway, argv: list[str]
) -> tuple[asyncio.Task[int], asyncio.Queue[str], io.StringIO, io.StringIO]:
    out, err, asked = io.StringIO(), io.StringIO(), asyncio.Queue[str]()
    env = {"PINECALL_URL": gateway.url, "PINECALL_KEY": KEY}
    running = asyncio.ensure_future(start(parse(argv), out, err, env, asked))
    await gateway.until(lambda: bool(gateway.commands_of("agent.configure")))
    return running, asked, out, err


def test_the_door_is_the_environments_alone_and_a_world_it_does_not_know_is_refused() -> None:
    with pytest.raises(CannotServe, match=NO_DOOR):
        client_from({"PINECALL_URL": "https://x"}, prod=False)
    with pytest.raises(CannotServe, match="sandbox or production, not staging"):
        client_from(
            {"PINECALL_URL": "https://x", "PINECALL_KEY": "k", "PINECALL_ENV": "staging"},
            prod=False,
        )
    assert (
        client_from({"PINECALL_URL": "https://x", "PINECALL_KEY": "k"}, prod=True).env
        == "production"
    )


async def test_the_first_line_is_the_registration_and_a_signal_drains_then_leaves(
    gateway: FakeGateway, tmp_path: Path
) -> None:
    running, asked, out, err = await started(gateway, flags_of(tmp_path))
    first = json.loads(out.getvalue().splitlines()[0])
    assert (first["type"], first["agent"], first["data"]["app"]) == (
        "agent.registered",
        "recepcion",
        "app_1",
    )
    asked.put_nowait(SIGNALLED)
    assert await running == 0
    assert err.getvalue() == "draining · 1 live call handed over\n"
    assert len(gateway.commands_of("agent.drain")) == 1


async def test_a_consoles_process_takes_no_call_it_did_not_open(
    gateway: FakeGateway, tmp_path: Path
) -> None:
    running, asked, _, _ = await started(gateway, flags_of(tmp_path, "--console"))
    data = gateway.commands_of("agent.register")[0]["data"]
    assert isinstance(data, dict)
    assert data["takes_unclaimed"] is False
    asked.put_nowait(STOPPED)
    assert await running == 0
    assert gateway.commands_of("agent.drain") == []


async def test_the_console_gets_the_panel_and_every_other_verb_is_refused_as_the_clis(
    gateway: FakeGateway, tmp_path: Path
) -> None:
    running, asked, _, _ = await started(gateway, flags_of(tmp_path))
    await gateway.emit(
        "recepcion",
        None,
        "dev.request",
        {"id": "d1", "verb": "view.render", "data": {"contact": "+34600", "call": "CA_1"}},
    )
    await gateway.emit(
        "recepcion", None, "dev.request", {"id": "d2", "verb": "goldens.roster", "data": {}}
    )
    await gateway.until(lambda: len(gateway.commands_of("dev.answer")) == 2)
    answers = {one["id"]: one for one in gateway.data_of("dev.answer")}
    assert answers["d1"]["result"] == {
        "name": "Ficha",
        "nodes": [{"tag": "text", "text": "+34600 en CA_1"}],
    }
    assert answers["d2"]["refused"] == {
        "status": 404,
        "detail": "this process answers only view.render: the console's other verbs are the CLI's",
    }
    asked.put_nowait(STOPPED)
    await running


async def test_a_second_signal_while_draining_leaves_at_once(tmp_path: Path) -> None:
    gateway = FakeGateway(holds_drain=True)
    await gateway.start()
    running, asked, _, err = await started(gateway, flags_of(tmp_path))
    asked.put_nowait(SIGNALLED)
    await gateway.until(lambda: bool(gateway.commands_of("agent.drain")))
    asked.put_nowait(SIGNALLED)
    assert await asyncio.wait_for(running, 2) == 0
    assert "draining" not in err.getvalue()
    await gateway.close()

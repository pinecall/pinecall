"""The reaper's loop: a part of a pass that fails is said, the other parts run, and the next pass comes."""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from pinecall_runtime.calls import tasks
from pinecall_runtime.calls.service.serving import Serving
from tests.conftest import until


# 2026-10-23: a pass that raised a pydantic error (a call whose start the seal could not read) ended
# the reaper on every gateway for good, and the calls another gateway had sealed held their seats.
async def test_a_pass_that_fails_does_not_end_the_reaper_nor_keep_the_calls_over_from_being_let_go(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passes: list[str] = []

    async def reap(_serving: Serving, _now: float) -> list[str]:
        passes.append("reap")
        raise ValueError("1 validation error for CallStarted\ncaller\n  Field required")

    async def hand_parked(_live: object, _registry: object) -> list[str]:
        passes.append("hand")
        return []

    def end_parked(_serving: Serving, _now: float) -> list[str]:
        passes.append("end")
        return []

    async def let_go(_serving: Serving, _now: float) -> list[str]:
        passes.append("let go")
        return []

    monkeypatch.setattr(tasks, "reap", reap)
    monkeypatch.setattr(tasks, "hand_parked", hand_parked)
    monkeypatch.setattr(tasks, "end_parked", end_parked)
    monkeypatch.setattr(tasks, "let_go", let_go)
    monkeypatch.setattr(tasks, "REAPED_EVERY_S", 0.01)
    reaper = asyncio.create_task(tasks.reap_forever(cast(Serving, SimpleNamespace(live=None, registry=None))))
    try:
        await until(lambda: passes.count("let go") >= 2)
        assert not reaper.done()
        assert passes[:4] == ["reap", "hand", "end", "let go"]
    finally:
        reaper.cancel()
        await asyncio.gather(reaper, return_exceptions=True)

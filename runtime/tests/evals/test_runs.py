"""The runs a gateway plays: the lease an agent is held under is renewed while the run plays, whatever a renewal met."""

import asyncio
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinecall_runtime.evals.service import runs
from pinecall_runtime.evals.service.runs import Runner
from tests.conftest import until


# A renewal that raised ended the loop that renews: the lease ran out under a run still playing, and
# another run took the agent it was driving.
async def test_a_renewal_that_failed_is_said_with_its_run_and_tried_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    renewed = 0

    async def leased(_runner: Runner, _run: str, _agent: str) -> bool:
        nonlocal renewed
        renewed += 1
        if renewed == 1:
            raise RuntimeError("the database did not answer")
        return True

    monkeypatch.setattr(Runner, "_leased", leased)
    monkeypatch.setattr(runs, "LEASED_S", 0.03)
    renewing = asyncio.create_task(Runner(cast(async_sessionmaker[AsyncSession], None))._renewed("run_1", "recepcion"))
    try:
        await until(lambda: renewed >= 3, 30)
        assert not renewing.done()
        assert "renewing the lease of an eval run failed on run_1" in caplog.text
    finally:
        renewing.cancel()
        await asyncio.gather(renewing, return_exceptions=True)

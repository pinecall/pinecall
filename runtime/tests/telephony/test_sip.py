"""The SIP rebuild: an org it cannot admit is refused alone, and the rebuild is tried again until whole."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pinecall_runtime.channels import service as channels
from pinecall_runtime.kit.handles import Handles
from pinecall_runtime.telephony.service import sip
from pinecall_runtime.telephony.service.sip import Rebuilt


# An org whose numbers raised anything but an SFU error ended the rebuild, and every org after it went
# unadmitted; the retry that waits for the SFU caught four classes and ended on any other.
async def test_an_org_whose_numbers_cannot_be_admitted_is_refused_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    async def orgs(_session: AsyncSession) -> list[str]:
        return ["org_a", "org_b", "org_c"]

    async def readmit(_session: AsyncSession, _handles: Handles, org: str) -> int:
        if org == "org_a":
            raise ValueError("1 validation error for CarrierAccount")
        return 2

    async def hand_overs(_session: AsyncSession, _handles: Handles) -> bool:
        raise RuntimeError("the sandbox's SFU said nothing sensible")

    monkeypatch.setattr(channels, "orgs_with_phones", orgs)
    monkeypatch.setattr(sip, "readmit", readmit)
    monkeypatch.setattr(sip, "_hand_overs_admitted", hand_overs)
    rebuilt = await sip.rebuild(cast(AsyncSession, None), cast(Handles, None))
    assert rebuilt == Rebuilt(numbers=4, refused=["org_a"], hand_over=False)


async def test_a_rebuild_that_raised_anything_is_tried_again_until_it_is_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    tries = 0

    @asynccontextmanager
    async def opened() -> AsyncGenerator[SimpleNamespace]:
        yield SimpleNamespace(commit=_committed)

    async def rebuild(_session: object, _handles: Handles) -> Rebuilt:
        nonlocal tries
        tries += 1
        if tries == 1:
            raise ValueError("a database that lags its code")
        if tries == 2:
            return Rebuilt(numbers=1, refused=["org_a"])
        return Rebuilt(numbers=2, refused=[])

    monkeypatch.setattr(sip, "rebuild", rebuild)
    handles = cast(Handles, SimpleNamespace(sessions=opened))
    assert await sip.rebuilt_until_whole(handles, wait_s=0.01) == Rebuilt(numbers=2, refused=[])
    assert tries == 3


async def _committed() -> None:
    return None

"""The SIP rebuild: an org it cannot admit is refused alone, and only what is owed is tried again until whole."""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from runtime.kit.crypto import Vault
from runtime.livekit import Servers
from runtime.telephony.service import rebuild
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.rebuild import NotWhole, Owed, Rebuilt

NO_SESSION = cast(AsyncSession, None)
NO_VAULT = cast(Vault, None)
NO_SERVERS: Servers = {}
NAMES = SipNames(domain="box.test", sip_domains={})


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The orgs a pass readmits, in order; org_a's numbers raise, the others' stand two each."""
    readmitted: list[str] = []

    async def orgs(_session: AsyncSession) -> list[str]:
        return ["org_a", "org_b", "org_c"]

    async def readmit(_session: AsyncSession, _vault: Vault, _servers: Servers, org: str) -> int:
        readmitted.append(org)
        if org == "org_a":
            raise ValueError("1 validation error for CarrierAccount")
        return 2

    async def hand_overs(*_: object) -> bool:
        raise RuntimeError("the sandbox's SFU said nothing sensible")

    monkeypatch.setattr(rebuild, "list_orgs_with_phones", orgs)
    monkeypatch.setattr(rebuild, "readmit", readmit)
    monkeypatch.setattr(rebuild.hand_over, "admit_hand_overs", hand_overs)
    return readmitted


# An org whose numbers raised anything but an SFU error ended the rebuild, and every org after it went
# unadmitted; the retry that waits for the SFU caught four classes and ended on any other.
async def test_an_org_whose_numbers_cannot_be_admitted_is_refused_alone(asked: list[str]) -> None:
    rebuilt = await rebuild.rebuild(NO_SESSION, NO_VAULT, NO_SERVERS, NAMES, Owed())
    assert rebuilt == Rebuilt(numbers=4, refused=["org_a"], hand_over=False)
    assert asked == ["org_a", "org_b", "org_c"]


# Until 2026-11 a pass that left one org refused rebuilt every org of the box again, once a minute.
async def test_a_pass_that_left_an_org_refused_owes_that_org_alone_until_it_stands(asked: list[str]) -> None:
    owed = Owed()
    assert not owed.nothing
    with pytest.raises(NotWhole):
        owed.settle(await rebuild.rebuild(NO_SESSION, NO_VAULT, NO_SERVERS, NAMES, owed))
    assert owed.orgs == ["org_a"]
    asked.clear()
    with pytest.raises(NotWhole):
        owed.settle(await rebuild.rebuild(NO_SESSION, NO_VAULT, NO_SERVERS, NAMES, owed))
    assert asked == ["org_a"]
    owed.settle(Rebuilt(numbers=2, refused=[]))
    assert owed.nothing

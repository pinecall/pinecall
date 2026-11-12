"""Who holds what on a gateway: a person's own phone, one at a time."""

from runtime.enums import Env
from runtime.live.parts import LiveParts
from tests.conftest import needs_the_database


# K F2 (2026-10-23): `line from` added a phone beside the one before, and `line forget` then took both.
@needs_the_database
async def test_a_persons_phone_said_again_replaces_the_one_before_and_forget_takes_the_one_left(
    live: LiveParts,
) -> None:
    holders = live.holders
    holders.route_phone(Env.sandbox, "+34607827824", "m_ana")
    holders.route_phone(Env.sandbox, "+34600000000", "m_ana")
    holders.route_phone(Env.sandbox, "+34611111111", "m_eva")
    assert holders.phones_of(Env.sandbox, "m_ana") == ["+34600000000"]
    assert holders.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]
    assert holders.forget_phones(Env.sandbox, "m_ana") == ["+34600000000"]
    assert holders.phones_of(Env.sandbox, "m_ana") == []
    assert holders.phones_of(Env.sandbox, "m_eva") == ["+34611111111"]

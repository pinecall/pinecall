"""The words a contact stops the messages with, or starts them again with, and what silences a thread."""

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.compliance.service import consents, keywords
from runtime.compliance.service.consents import Given
from runtime.enums import ConsentKind, Env
from tests.conftest import Tenant, needs_the_database


@pytest.mark.parametrize(
    "text",
    [
        "STOP",
        "stop",
        " Stop. ",
        "stop!",
        "STOPALL",
        "Unsubscribe",
        "cancel",
        "END",
        "quit",
        "REVOKE",
        "OptOut",
        "Opt-out",
        "opt out",
    ],
)
def test_a_message_that_is_a_stop_word_and_nothing_else_stops(text: str) -> None:
    assert keywords.keyword_of(text) == "stop"


@pytest.mark.parametrize(
    "text", ["stop by at five", "please stop", "can I cancel my visit?", "the end", "", None, "ok"]
)
def test_a_sentence_that_holds_a_stop_word_is_a_message_like_any_other(text: str | None) -> None:
    """Whole messages alone are words: the rest is the model's to read, and to act on with its tool."""
    assert keywords.keyword_of(text) is None


def test_start_and_help_are_words_too_and_an_org_adds_the_ones_its_contacts_stop_with() -> None:
    assert [keywords.keyword_of(text) for text in ("START", "unstop", "Yes", "HELP", "info")] == [
        "start",
        "start",
        "start",
        "help",
        "help",
    ]
    assert keywords.keyword_of("¡Baja!") is None
    assert keywords.keyword_of("¡Baja!", ("BAJA", "alto")) == "stop"
    assert keywords.keyword_of("Alto", ("BAJA", "alto")) == "stop"


@needs_the_database
async def test_a_thread_is_silenced_by_an_opt_out_made_in_writing_and_by_no_other(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A number on the list for the phone that then writes is answered; one that texted STOP is not, until START."""
    scope = Scope(tenant.org, Env.sandbox)
    number = f"+1555{secrets.randbelow(10**7):07d}"
    async with sessions.begin() as session:
        assert not await keywords.refuses_messages(session, scope, number)
        by_hand = Given(kind=ConsentKind.opt_out, source=consents.ASKED_BY_HAND, given_by="a person")
        await consents.give_consent(session, scope, number, by_hand)
        assert not await keywords.refuses_messages(session, scope, number)
        await keywords.stop_writing_to(
            session, scope, number, source=keywords.TEXTED_STOP, text="STOP", call=None, by="contact"
        )
        assert await keywords.refuses_messages(session, scope, number)
        assert await consents.standing_of(session, scope, number) == "opted_out"
        await keywords.start_writing_to(session, scope, number, text="START")
        assert not await keywords.refuses_messages(session, scope, number)
        assert await consents.standing_of(session, scope, number) == "consented"
        # The other env keeps a list of its own.
        assert not await keywords.refuses_messages(session, Scope(tenant.org, Env.production), number)


@needs_the_database
async def test_an_email_contact_is_kept_on_the_list_by_their_address(
    sessions: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    """A contact who asked the agent, in an email, for no more is refused by their address."""
    scope = Scope(tenant.org, Env.sandbox)
    address = f"ana-{secrets.token_hex(3)}@Example.org"
    async with sessions.begin() as session:
        assert not await keywords.refuses_messages(session, scope, address)
        await keywords.stop_writing_to(
            session, scope, address, source=keywords.ASKED_THE_AGENT_IN_WRITING, text="no more", call=None, by="agent"
        )
        assert await keywords.refuses_messages(session, scope, address.lower())

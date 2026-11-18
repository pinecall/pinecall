"""What a contact texts to be written to no more, or again, or to ask who writes: the words, and what stands."""

import re
import unicodedata
from collections.abc import Iterable
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from runtime.actor import Scope
from runtime.compliance.service import consents
from runtime.compliance.service.consents import Given
from runtime.enums import ConsentKind

type Keyword = Literal["stop", "start", "help"]

# The words the FCC names as reasonable on their face (47 CFR 64.1200(a)(10), in force since
# 2025-04-11) and the ones Twilio takes itself on a long code: a contact who texts one of these, and
# nothing else, is written to no more. An org adds the words of its own contacts' language.
STOP_WORDS = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "revoke", "optout", "opt out"})
# What lifts it, for a contact who is on the list; anybody else who writes "yes" is answering the agent.
START_WORDS = frozenset({"start", "unstop", "yes"})
HELP_WORDS = frozenset({"help", "info"})
TEXTED_STOP = "the contact texted a word that stops the messages"
TEXTED_START = "the contact texted a word that starts them again"
ASKED_THE_AGENT_IN_WRITING = "the contact asked the agent, in writing"
IN_WRITING = frozenset({TEXTED_STOP, ASKED_THE_AGENT_IN_WRITING})
# What a contact the agent took off the list is told when the org wrote no sentence of its own: the
# carrier confirmed nothing, since it saw no word of its own.
TAKEN_OFF = "You will not receive more messages from this number. Reply START to get them again."
_PUNCTUATION = re.compile(r"[^\w\s]|_")
_SPACES = re.compile(r"\s+")


# The whole message is the word: "stop by at five" stops nothing. Case, accents, a full stop, an
# exclamation mark and a hyphen say nothing ("STOP.", "Opt-out", "¡Alto!").
def word_of(text: str | None) -> str:
    """A message as the word it may be: lowered, with no accent and no punctuation."""
    plain = unicodedata.normalize("NFKD", text or "")
    plain = "".join(sign for sign in plain if not unicodedata.combining(sign))
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", plain)).strip().casefold()


def keyword_of(text: str | None, more_stop_words: Iterable[str] = ()) -> Keyword | None:
    """Which of the three a message is, when it is one of them and nothing else."""
    said = word_of(text)
    if said in STOP_WORDS or said in {word_of(word) for word in more_stop_words}:
        return "stop"
    if said in START_WORDS:
        return "start"
    return "help" if said in HELP_WORDS else None


# A number on the list for the phone ("do not call me") that then writes is answered: the one who
# wrote first asked for the answer. What silences a thread is an opt-out made in writing.
async def refuses_messages(session: AsyncSession, scope: Scope, number: str) -> bool:
    """Whether the number's newest fact is an opt-out it made in writing: by a word, or by asking the agent."""
    newest = await consents.newest_of(session, scope, number)
    return newest is not None and newest.kind is ConsentKind.opt_out and newest.source in IN_WRITING


async def stop_writing_to(
    session: AsyncSession, scope: Scope, number: str, *, source: str, text: str | None, call: str | None, by: str
) -> None:
    """Put the number on the list at the contact's own word, with the words and the call it was said on."""
    given = Given(kind=ConsentKind.opt_out, source=source, given_by=by, text=text, call=call)
    await consents.give_consent(session, scope, number, given)


async def start_writing_to(session: AsyncSession, scope: Scope, number: str, *, text: str | None) -> None:
    """Lift the list for the number at the contact's own word: an express consent, with the words."""
    given = Given(kind=ConsentKind.express, source=TEXTED_START, given_by="contact", text=text)
    await consents.give_consent(session, scope, number, given)

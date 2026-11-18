"""A call's first sentences in its language: the written ones, the ones a model wrote once and the box kept."""

import os
import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.agents.service import sentences
from runtime.agents.service.sentences import CALLING_FOR, MAY_BE_RECORDED, Sentences, read_written
from runtime.kit.crypto import Vault


def a_vault() -> Vault:
    return Vault(os.environ["PINECALL_VAULT_KEY"])


# A language no vendor knows by this name, so no test meets another's row: three letters, as a tag is.
def a_language() -> str:
    return "q" + secrets.choice("qwxyz") + secrets.choice("abcdefghijklmnopqrstuvwxyz")


def test_every_language_written_here_has_both_sentences_and_names_the_org_once() -> None:
    assert set(MAY_BE_RECORDED) == set(CALLING_FOR)
    assert [language for language, said in CALLING_FOR.items() if said.count("{org}") != 1] == []
    assert CALLING_FOR["pt"].format(org="Al Noor") == "Aqui fala um assistente automático em nome de Al Noor."


def test_a_models_answer_is_read_as_the_two_sentences_whatever_it_wrote_around_them() -> None:
    answered = (
        'Here you go:\n{"calling_for": "Huyu ni msaidizi wa {org}.", '
        '"may_be_recorded": "Simu  hii\\ninaweza kurekodiwa."}'
    )
    assert read_written(answered) == Sentences("Huyu ni msaidizi wa {org}.", "Simu hii inaweza kurekodiwa.")


@pytest.mark.parametrize(
    "answered",
    [
        "I cannot help with that.",
        '{"calling_for": "Huyu ni msaidizi.", "may_be_recorded": "Simu hii inaweza kurekodiwa."}',
        '{"calling_for": "Msaidizi wa {org} na {org}.", "may_be_recorded": "Simu."}',
        '{"calling_for": "Msaidizi wa {org}.", "may_be_recorded": ""}',
        '{"calling_for": "Msaidizi wa {org}.", "may_be_recorded": "Simu ya {org}."}',
        '{"calling_for": "Msaidizi wa {org}."}',
        '["calling_for"]',
    ],
)
def test_an_answer_that_is_not_the_two_sentences_with_the_org_named_once_is_none(answered: str) -> None:
    assert read_written(answered) is None


async def test_a_language_written_here_is_said_as_written_by_any_of_its_tags_and_its_main_one_of_several(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        assert (await sentences.sentences_in(session, a_vault(), "pt-BR")).may_be_recorded == MAY_BE_RECORDED["pt"]
        assert (await sentences.sentences_in(session, a_vault(), "hi, en")).may_be_recorded == MAY_BE_RECORDED["hi"]
        assert (await sentences.sentences_in(session, a_vault(), None)).may_be_recorded == MAY_BE_RECORDED["en"]


# The fake vendor's model says back what it was asked: not the two sentences.
async def test_a_model_that_answers_anything_else_leaves_the_english_ones_and_nothing_kept(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    language = a_language()
    async with sessions.begin() as session:
        said = await sentences.sentences_in(session, a_vault(), language)
        assert said == Sentences(CALLING_FOR["en"], MAY_BE_RECORDED["en"])
        assert await sentences.read_sentences(session, language) == said


async def test_a_language_nobody_wrote_is_written_once_and_kept_for_every_call_after(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    language, asked = a_language(), [0]
    written = Sentences("Huyu ni msaidizi wa {org}.", "Simu hii inaweza kurekodiwa.")

    async def write(session: AsyncSession, vault: Vault, spoken: str) -> Sentences:
        asked[0] += 1
        return written

    monkeypatch.setattr(sentences, "_write", write)
    async with sessions.begin() as session:
        assert await sentences.sentences_in(session, a_vault(), language) == written
    async with sessions.begin() as session:
        assert await sentences.sentences_in(session, a_vault(), f"{language}-KE") == written
        assert await sentences.read_sentences(session, language) == written
    assert asked == [1]

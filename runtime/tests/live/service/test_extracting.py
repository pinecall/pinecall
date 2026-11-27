"""A flow's model, asked outside a call: the object it read, and the request metered on the agent's log."""

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.actor import Scope
from runtime.calls import service as calls
from runtime.calls.context import log_name
from runtime.enums import Env
from runtime.exceptions import Conflict, UpstreamError
from runtime.live.service import extracting
from runtime.providers import service as providers
from runtime.providers.service.questions import Answer, Line
from runtime.providers.stage import Running
from runtime.wire.metrics import LLMModelUsage
from tests.conftest import Tenant, needs_the_database
from tests.live.conftest import Side

A_NOTICE = {"type": "object", "properties": {"phone": {"type": "string"}, "name": {"type": "string"}}}
SPENT = LLMModelUsage(provider="gemini", model="flash-lite", input_tokens=3080, output_tokens=60)


class FakeModel:
    """A model that answers every question with the arguments it was given, or in words when given none."""

    def __init__(self, arguments: Mapping[str, object] | None) -> None:
        self.arguments = arguments
        self.asked: list[tuple[Sequence[Line], Mapping[str, Any]]] = []

    async def ask_by_tool(self, lines: Sequence[Line], tool: Mapping[str, Any], **_: object) -> Answer:
        self.asked.append((lines, tool))
        return Answer(text="I cannot tell.", arguments=self.arguments, usage=SPENT)


def _on_a_model(monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    @asynccontextmanager
    async def opened(running: Running) -> AsyncGenerator[FakeModel]:
        yield model

    def chosen(*_: object, **__: object) -> Running:
        return Running(vendor="google", credentials="the box's", model="gemini-3.5-flash-lite", lent=True)

    monkeypatch.setattr(providers, "open_answerer", opened)
    monkeypatch.setattr(providers, "stage_on_its_key", chosen)


def _asked(agent: str) -> extracting.Extracting:
    words = "Hay una nueva consulta de Soledad, teléfono 11 3125 8777."
    return extracting.Extracting("front-desk-app", "notice", "run_8f4a2c", agent, words, A_NOTICE, "Who asked.")


async def _spent(sessions: async_sessionmaker[AsyncSession], agent: str) -> list[dict[str, Any]]:
    async with sessions() as session:
        entries = await calls.list_entries(session, log_name(None, agent))
    return [entry.data for entry in entries if entry.type == "model.spent"]


@needs_the_database
async def test_the_model_reads_the_words_into_the_object_and_its_request_is_one_written_turn(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The schema is the tool the model must call; what it spent is on the agent's log, the env said."""
    model = FakeModel({"phone": "+541131258777", "name": "Soledad"})
    _on_a_model(monkeypatch, model)
    agent = f"reader-{tenant.org[-6:]}"
    async with sessions.begin() as session:
        read = await extracting.extract(session, side.parts, Scope(tenant.org, Env.sandbox), _asked(agent))
    assert read == {"phone": "+541131258777", "name": "Soledad"}
    [(lines, tool)] = model.asked
    assert (tool["name"], tool["parameters"]) == ("extracted", A_NOTICE)
    assert "Who asked." in lines[0].text and lines[1].text.startswith("Hay una nueva consulta")
    [spent] = await _spent(sessions, agent)
    assert (spent["env"], spent["turns"], spent["run"], spent["own_key"]) == ("sandbox", 1, "run_8f4a2c", False)
    assert spent["usage"][0]["input_tokens"] == 3080


@needs_the_database
async def test_a_model_that_will_not_answer_by_the_schema_is_refused_and_still_metered(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    _on_a_model(monkeypatch, FakeModel(None))
    agent = f"reader-{tenant.org[-6:]}"
    with pytest.raises(UpstreamError, match="answered without calling extracted"):
        async with sessions.begin() as session:
            await extracting.extract(session, side.parts, Scope(tenant.org, Env.sandbox), _asked(agent))
    assert len(await _spent(sessions, agent)) == 1


@needs_the_database
async def test_an_agent_another_org_owns_is_refused_before_anything_is_asked(
    side: Side, sessions: async_sessionmaker[AsyncSession], tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel({"phone": "+541131258777"})
    _on_a_model(monkeypatch, model)
    agent = f"taken-{tenant.org[-6:]}"
    async with sessions.begin() as session:
        await calls.claim_agent_log(session, agent, "org_somebody_else")
    with pytest.raises(Conflict, match="is another org's"):
        async with sessions.begin() as session:
            await extracting.extract(session, side.parts, Scope(tenant.org, Env.sandbox), _asked(agent))
    assert model.asked == []

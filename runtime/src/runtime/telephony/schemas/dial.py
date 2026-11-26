"""The bodies of a dial and of a text or email the agent sends first: the far end, the consent, the call it became."""

import json
from typing import Literal

from pydantic import Field, field_validator

from runtime.enums import Env
from runtime.kit.schemas import Row, Schema
from runtime.kit.text import Json, JsonObject
from runtime.wire.parts import Projection

# What a dial may carry into its call: a visit, a reason, an id, never a document.
OPENING_BYTES = 8192


class Consent(Schema):
    """The consent a call runs on: express or written, where it came from, the words, a proof."""

    kind: Literal["express", "written"]
    source: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=500)


class DialRequest(Schema):
    """POST /v1/agents/{slug}/dial: the far end, the org's number it is shown, the consent, what the call opens with."""

    to: str
    from_: str | None = Field(None, alias="from")
    consent: Consent | None = None
    # The state the agent's call opens in and what its `call.started` carries, as a web call's token names them.
    state: JsonObject = Field(default_factory=dict[str, Json])
    metadata: JsonObject = Field(default_factory=dict[str, Json])
    # The words this call opens with, over the agent's own greeting; and what this call is for, which
    # the agent reads for the whole call and, with no greeting given, opens on.
    greeting: str | None = Field(default=None, min_length=1, max_length=500)
    instruction: str | None = Field(default=None, min_length=1, max_length=2000)
    # What the log token handed back reads the call through.
    log: Projection = "tenant"

    # Both ride the room's dispatch, which the media plane keeps small.
    @field_validator("state", "metadata")
    @classmethod
    def _fits_a_dispatch(cls, given: JsonObject) -> JsonObject:
        if len(json.dumps(given)) > OPENING_BYTES:
            raise ValueError(f"what a dialled call opens with is {OPENING_BYTES} bytes of JSON at most")
        return given


class DialResponse(Row):
    """POST /v1/agents/{slug}/dial, the answer."""

    call: str
    agent: str
    to: str
    from_: str = Field(alias="from")
    env: Env
    log_token: str


class TextRequest(Schema):
    """POST /v1/agents/{slug}/text: the contact, the words, the org's number or address they leave from, the consent."""

    # A number is sent an SMS; an address (it holds an `@`) an email, under `subject`.
    to: str
    # An email's alone may be left out: the agent then writes its first words itself.
    text: str | None = Field(default=None, min_length=1, max_length=1600)
    from_: str | None = Field(None, alias="from")
    consent: Consent | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    # A dial's: what the call's `call.started` carries, and what the call is for, which the agent reads
    # for the whole conversation and, with no `text`, opens on.
    metadata: JsonObject = Field(default_factory=dict[str, Json])
    instruction: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("metadata")
    @classmethod
    def _fits_a_dispatch(cls, given: JsonObject) -> JsonObject:
        if len(json.dumps(given)) > OPENING_BYTES:
            raise ValueError(f"what a written call opens with is {OPENING_BYTES} bytes of JSON at most")
        return given


class TextResponse(Row):
    """POST /v1/agents/{slug}/text, the answer: the conversation the text was said on."""

    call: str
    agent: str
    to: str
    from_: str = Field(alias="from")
    env: Env


class TemplateRequest(Schema):
    """POST /v1/agents/{slug}/template: the contact, the template, what fills it, the number it leaves from."""

    to: str
    template: str = Field(min_length=1, max_length=512)
    # Meta's code of the language the template was approved in: `es_AR`, `en_US`.
    language: str = Field(min_length=2, max_length=16)
    # What fills the body's {{1}}, {{2}}…, in order.
    variables: list[str] = Field(default_factory=list[str], max_length=32)
    from_: str | None = Field(None, alias="from")


class TemplateResponse(Row):
    """POST /v1/agents/{slug}/template, the answer: where it went, and whether Meta was asked at all."""

    agent: str
    to: str
    from_: str | None = Field(alias="from")
    env: Env
    template: str
    # The sandbox's: nothing was asked of Meta, nobody was written to, and there is no id.
    simulated: bool
    message_id: str | None

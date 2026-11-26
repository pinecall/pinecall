"""A vendor's no in our words: its refusal the request's, its silence and its own failures the vendor's."""

import re
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from http import HTTPStatus

from livekit.agents import APIConnectionError, APIError, APIStatusError, APITimeoutError

from runtime.enums import Stage
from runtime.exceptions import UpstreamError, ValidationError
from runtime.kit.text import a_mapping
from runtime.providers.service.plugins import INFERENCE, INFERENCE_MODULE, PLUGINS

# A status at or past it is the vendor failing, not what was asked of it.
THE_VENDORS_OWN = 500

# What a vendor answers when the account it was asked on cannot pay: its body's `code` or `type`, or its
# own sentence. Said with a 429 by OpenAI ("You have no credits remaining", `insufficient_quota`) and
# xAI (a team's spending limit), with a 400 by Anthropic ("credit balance is too low"), and with a bare 402
# by xAI's realtime handshake. Unlike a rate
# limit, which the same status says too, retrying it changes nothing until a person pays.
UNPAID_CODES = frozenset(
    {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active", "access_terminated", "credit_exhausted"}
)
UNPAID_WORDS = re.compile(
    r"no credits remaining|credit balance is too low|exceeded your current quota|spending.limit|billing.hard.limit"
    r"|\b402 Payment Required",
    re.IGNORECASE,
)

# A vendor that will not open a connection says so with a status the client reports as the cause of a
# "connection error": xAI answers a realtime handshake `402` for an account with no credit, and the
# plugin raises "client connection error". The status is read a few causes down, no further.
PAYMENT_REQUIRED = 402
A_REFUSAL = 400
CAUSES_READ = 4

# The sentence a use case says of a vendor that did not answer, given the words the silence came with.
type Silence = Callable[[str], str]

# A component that failed is named in its error's label: `label='livekit.plugins.deepgram.stt.STT'`.
LABELLED = re.compile(
    rf"label='(?:{re.escape(PLUGINS)}\.(?P<plugin>\w+)|(?P<inference>{re.escape(INFERENCE_MODULE)}))\."
)
# The label places it too: the stage is the plugin's module, `livekit.plugins.google.llm.LLM`.
STAGE_IN = re.compile(r"plugins\.\w+\.(?P<stage>llm|stt|tts)\b")
# A stage as an org reads it, in an alert and in a call's own log.
STAGE_NAMED = {Stage.llm: "model", Stage.stt: "transcription", Stage.tts: "voice"}


# The one translation of livekit's errors. A vendor that turns down what it was asked (a typo in a
# voice's id, a model it does not run, a key it does not know) is the request's fault, refused as a
# setting is refused; a vendor that does not answer, or fails on its side, is the vendor's. The use
# case opens this once, around everything it asks of the vendor: what runs below lets livekit's
# errors through, so nothing is translated twice and nobody reads a cause back out of our own error.
@contextmanager
def refusing(vendor: str, what: str, *, silence: Silence | None = None) -> Generator[None]:
    """The vendor's no, said once: `{vendor} refused {what}`, in its own words after the colon."""
    try:
        yield
    except (APIConnectionError, APITimeoutError) as silent:
        words = _word(vendor, what, silent) if silence is None else silence(sentence_of(silent))
        raise UpstreamError(words, vendor=vendor, retryable=True) from silent
    except APIStatusError as answered:
        if answered.status_code < THE_VENDORS_OWN:
            raise ValidationError(_word(vendor, what, answered)) from answered
        words = _word(vendor, what, answered)
        raise UpstreamError(words, vendor=vendor, answered=answered.status_code, retryable=True) from answered
    except APIError as refused:
        raise ValidationError(_word(vendor, what, refused)) from refused


# The three sentences a vendor's no is said in, wherever it is said: thrown by `refusing`, or written
# on a live call's log by `say_failure`.
def _word(vendor: str, what: str, refused: APIError) -> str:
    if isinstance(refused, APIConnectionError | APITimeoutError):
        status = status_behind(refused)
        if status is not None and status < THE_VENDORS_OWN:
            return f"{vendor} refused {what}: it answered the connection {status} {_phrase(status)}"
        return f"{vendor} did not answer: {sentence_of(refused)}"
    if isinstance(refused, APIStatusError) and refused.status_code >= THE_VENDORS_OWN:
        return f"{vendor} failed on its side ({refused.status_code}): {sentence_of(refused)}"
    return f"{vendor} refused {what}: {sentence_of(refused)}"


# A vendor SDK puts its whole body in the message (`Error code: 401 - {'message': …}`): the
# vendor's own sentence is the body's `message`, at its top or under `error`, when it has one.
def sentence_of(refused: APIError) -> str:
    """What the vendor said, in its words."""
    body = refused.body
    holders: list[Mapping[str, object]] = []
    if a_mapping(body):
        holders.append(body)
        nested = body.get("error")
        if a_mapping(nested):
            holders.append(nested)
    for holder in holders:
        said = holder.get("message")
        if isinstance(said, str) and said.strip():
            return said.strip()
    return refused.message


def status_behind(refused: BaseException) -> int | None:
    """The HTTP status a vendor refused with, on the error itself or on what caused it; None when it gave none."""
    cause: BaseException | None = refused
    for _ in range(CAUSES_READ):
        if cause is None:
            return None
        for name in ("status_code", "status"):
            status: object = getattr(cause, name, None)
            if isinstance(status, int) and not isinstance(status, bool) and status >= A_REFUSAL:
                return status
        cause = cause.__cause__ or cause.__context__
    return None


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return ""


def is_unpaid(refused: APIError) -> bool:
    """Whether the vendor refused because the account it was asked on cannot pay: no credit, a quota or limit spent."""
    if status_behind(refused) == PAYMENT_REQUIRED:
        return True
    body = refused.body
    holders: list[Mapping[str, object]] = []
    if a_mapping(body):
        holders.append(body)
        nested = body.get("error")
        if a_mapping(nested):
            holders.append(nested)
    for holder in holders:
        if any(str(holder.get(key) or "") in UNPAID_CODES for key in ("code", "type")):
            return True
    return says_unpaid(f"{sentence_of(refused)} {refused.message}")


# A realtime model's refusal reaches a call's log as words alone, its vendor's code among them; and a
# connection refused for payment as the status it was answered with (`_word`).
def says_unpaid(text: str) -> bool:
    """Whether these words are a vendor's refusal of an account that cannot pay."""
    return UNPAID_WORDS.search(text) is not None or any(code in text for code in UNPAID_CODES)


def vendor_named_in(text: str) -> str:
    """The vendor whose plugin a component's error names, "" when it names none."""
    found = LABELLED.search(text)
    if found is None:
        return ""
    return INFERENCE if found["inference"] else found["plugin"]


def stage_named_in(text: str) -> Stage | None:
    """The stage of the component an error names, None when it names none."""
    found = STAGE_IN.search(text)
    return None if found is None else Stage(found["stage"])


def name_stage(stage: Stage) -> str:
    """A stage as an org reads it: the model, the transcription, the voice."""
    return STAGE_NAMED[stage]


# What a live call's log says of a component that failed. Its first line is the reason as a person
# reads it, in the sentences `refusing` says a vendor's no with. livekit's own account goes under it,
# whole: it names the plugin, where the alerts and the gateway's counters read the vendor and the
# stage, and it carries the vendor's request id. Until 2026-11-16 that account alone was the message:
# for a key with no credit, `pinecall chat` and the alert read `type='llm_error' timestamp=…`.
def say_failure(failed: object) -> str:
    """A failed component in our words, livekit's own account of it on the lines under."""
    own = str(failed)
    stage = stage_named_in(own)
    vendor = vendor_named_in(own) or "the vendor"
    what = "this call" if stage is None else f"this call's {name_stage(stage)}"
    cause: object = getattr(failed, "error", None)
    if isinstance(cause, APIError):
        return f"{_word(vendor, what, cause)}\n{own}"
    said = "" if cause is None else f": {cause}"
    return f"{vendor} failed {what}{said}\n{own}"

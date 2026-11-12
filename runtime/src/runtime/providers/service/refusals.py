"""A vendor's no in our words: its refusal the request's, its silence and its own failures the vendor's."""

import re
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager

from livekit.agents import APIConnectionError, APIError, APIStatusError, APITimeoutError

from runtime.exceptions import UpstreamError, ValidationError
from runtime.kit.text import a_mapping
from runtime.providers.service.plugins import INFERENCE, INFERENCE_MODULE, PLUGINS

# A status at or past it is the vendor failing, not what was asked of it.
THE_VENDORS_OWN = 500

# The sentence a use case says of a vendor that did not answer, given the words the silence came with.
type Silence = Callable[[str], str]

# A component that failed is named in its error's label: `label='livekit.plugins.deepgram.stt.STT'`.
LABELLED = re.compile(
    rf"label='(?:{re.escape(PLUGINS)}\.(?P<plugin>\w+)|(?P<inference>{re.escape(INFERENCE_MODULE)}))\."
)


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
        said = sentence_of(silent)
        words = f"{vendor} did not answer: {said}" if silence is None else silence(said)
        raise UpstreamError(words, vendor=vendor, retryable=True) from silent
    except APIStatusError as answered:
        if answered.status_code < THE_VENDORS_OWN:
            raise ValidationError(f"{vendor} refused {what}: {sentence_of(answered)}") from answered
        words = f"{vendor} failed on its side ({answered.status_code}): {sentence_of(answered)}"
        raise UpstreamError(words, vendor=vendor, answered=answered.status_code, retryable=True) from answered
    except APIError as refused:
        raise ValidationError(f"{vendor} refused {what}: {sentence_of(refused)}") from refused


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


def vendor_named_in(text: str) -> str:
    """The vendor whose plugin a component's error names, "" when it names none."""
    found = LABELLED.search(text)
    if found is None:
        return ""
    return INFERENCE if found["inference"] else found["plugin"]

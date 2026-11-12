"""The record's dependencies: the keys that open it, who reads a log, a call a reader may read, the engine's objects."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from runtime.accounts import service as accounts
from runtime.actor import Actor
from runtime.auth import Authenticator, actor_of, authorization_of
from runtime.calls.log.feeds import Feeds
from runtime.calls.log.logs import Logs
from runtime.calls.log.relay import Relay
from runtime.calls.log.store import Store
from runtime.calls.log.writer import Writer
from runtime.calls.recordings import Recordings
from runtime.calls.service.lists import OrgsCall, get_call_of_org
from runtime.calls.service.prompts import Prompts
from runtime.calls.service.reading import NOT_YOURS, Readable, Reader, Visit, get_readable, record_read
from runtime.enums import KeyScope, ReadKind
from runtime.exceptions import Forbidden, Unauthorized
from runtime.kit.text import is_a_jwt
from runtime.postgres import Session

READ_WITH_A_KEY = "a log is read with a key, or with a token of that call"
A_LIST_TAKES_A_KEY = "a list of calls is read with a key, not a call's token"

CallsKey = Annotated[Actor, Depends(Authenticator(KeyScope.calls))]
UsageKey = Annotated[Actor, Depends(Authenticator(KeyScope.usage))]
# A worker asks with its fleet's key; a tenant's own worker with an app key.
WorkerKey = Annotated[Actor, Depends(Authenticator(KeyScope.app, KeyScope.fleet))]


# ── what the lifespan built ──


def writer_of(connection: HTTPConnection) -> Writer:
    """The one writer that numbers every log of this process."""
    writer: Writer = connection.state.writer
    return writer


def log_store_of(connection: HTTPConnection) -> Store:
    """The log's tables as the engine reaches them, on sessions of its own."""
    store: Store = connection.state.log_store
    return store


def relay_of(connection: HTTPConnection) -> Relay:
    """What tells every gateway what any of them wrote."""
    relay: Relay = connection.state.relay
    return relay


def feeds_of(connection: HTTPConnection) -> Feeds:
    """The feeds: an org's in each env, the box's, and the one that wakes the usage's readers."""
    feeds: Feeds = connection.state.feeds
    return feeds


def logs_of(connection: HTTPConnection) -> Logs:
    """The logs open in this process, by name."""
    logs: Logs = connection.state.logs
    return logs


def recordings_of(connection: HTTPConnection) -> Recordings:
    """Where this box keeps its calls' audio: the bucket its settings name, else its disk."""
    recordings: Recordings = connection.state.recordings
    return recordings


def prompts_of(connection: HTTPConnection) -> Prompts:
    """The blocks of prompt this process kept already."""
    prompts: Prompts = connection.state.prompts
    return prompts


TheWriter = Annotated[Writer, Depends(writer_of)]
TheLogStore = Annotated[Store, Depends(log_store_of)]
TheRelay = Annotated[Relay, Depends(relay_of)]
TheFeeds = Annotated[Feeds, Depends(feeds_of)]
TheLogs = Annotated[Logs, Depends(logs_of)]
TheRecordings = Annotated[Recordings, Depends(recordings_of)]
ThePrompts = Annotated[Prompts, Depends(prompts_of)]


# ── what is handed in from above ──


# A token of one call is signed and read by the live side, above this domain (accounts-3): whatever
# reads one is handed in under `visits`. Until it is, a call's token opens nothing here.
class Visits(Protocol):
    """What reads a token of one call."""

    def read(self, token: str) -> Visit | None:
        """What a token of ours says; None for anything else, whatever the reason."""
        ...


def visits_of(connection: HTTPConnection) -> Visits:
    """What reads a call's token, as the lifespan handed it in."""
    visits: Visits = connection.state.visits
    return visits


# ── who reads ──


# ?token= only for a token of ours: EventSource sets no header, and a key in a URL would leak.
# A worker reads the call it serves with the fleet's key and names no scope to do it, since the
# call's head row says whose it is: only a call's own reading endpoints (its events, its state,
# its recording) let that key in.
def reading(*opens: KeyScope) -> Callable[[Request], Awaitable[Reader]]:
    """A dependency that lets through a key that opens one of the scopes, or a call's token."""

    async def read(request: Request) -> Reader:
        data = authorization_of(request) or request.query_params.get("token")
        if data is None:
            raise Unauthorized(READ_WITH_A_KEY)
        if is_a_jwt(data):
            visit = visits_of(request).read(data)
            if visit is None:
                raise Unauthorized(READ_WITH_A_KEY)
            return Reader(visit=visit)
        actor = actor_of(request)
        if actor is None:
            raise Unauthorized(READ_WITH_A_KEY)
        if opens and not actor.opens(*opens):
            raise Forbidden(f"this key does not open {' or '.join(sorted(opens))}")
        _check_agent_named(request, actor)
        return Reader(actor=actor)

    return read


ReaderDep = Annotated[Reader, Depends(reading(KeyScope.calls))]


def the_listing_key(reader: ReaderDep) -> Actor:
    """The key a list of calls is read with; a call's token lists nothing."""
    return _key_of(reader, A_LIST_TAKES_A_KEY)


def the_reading_key(reader: ReaderDep) -> Actor:
    """The key an agent's log or the org's feed is read with; a call's token reads its own call alone."""
    return _key_of(reader, NOT_YOURS)


ListingKey = Annotated[Actor, Depends(the_listing_key)]
ReadingKey = Annotated[Actor, Depends(the_reading_key)]


# The call loaded and allowed for whoever reads it, and the read written down: one dependency, so an
# endpoint cannot read a call without asking whose it is. Until 2026-11 each of seven bodies called
# the check itself, and four the record after it.
def reading_call(what: ReadKind, *opens: KeyScope) -> Callable[..., Awaitable[Readable]]:
    """A dependency: the path's call as its reader may read it, the read of it recorded as `what`."""
    read = reading(*opens)

    async def load(call: str, session: Session, reader: Annotated[Reader, Depends(read)]) -> Readable:
        readable = await get_readable(session, reader, call)
        await record_read(session, reader, call, what)
        return readable

    return load


TheReadableCall = Annotated[Readable, Depends(reading_call(ReadKind.log, KeyScope.calls, KeyScope.fleet))]
# The prompt is the operator's and the app's words: a key's read, and never the fleet's.
ThePromptedCall = Annotated[Readable, Depends(reading_call(ReadKind.log, KeyScope.calls))]
TheRecordedCall = Annotated[Readable, Depends(reading_call(ReadKind.recording, KeyScope.calls, KeyScope.fleet))]


# By the call's head, which says whose it is: for what is read of a call beside its log (the settings
# it was built on).
async def load_call_of_org(call: str, actor: CallsKey, session: Session) -> OrgsCall:
    """The path's call, one of the key's org; another org's, or nobody's, is the same 404."""
    return await get_call_of_org(session, actor.org, call)


TheOrgsCall = Annotated[OrgsCall, Depends(load_call_of_org)]


def _key_of(reader: Reader, refusal: str) -> Actor:
    if reader.actor is None:
        raise Forbidden(refusal)
    return reader.actor


# The agent an endpoint names in its path or its query; a body's agent is checked by its endpoint.
def _check_agent_named(request: Request, actor: Actor) -> None:
    for slug in (request.path_params.get("slug"), request.query_params.get("agent")):
        if slug:
            accounts.check_agent(actor, slug)

"""The bodies of the routes endpoints the operator calls."""

from pinecall_runtime.enums import Channel, Env
from pinecall_runtime.kit.schemas import Schema
from pinecall_runtime.wire.base import WireModel


class RouteRequest(WireModel):
    """POST /v1/ops/routes: which org's agent answers a number, on a channel, in an env."""

    org: str
    number: str
    agent: str
    channel: Channel
    env: Env = Env.production


class RouteRow(WireModel):
    """One route as the operator lists it."""

    org: str
    number: str
    agent: str
    channel: Channel
    env: Env
    managed: bool


class RouteQuery(Schema):
    """What a worker asks of the routes: the number a call rang, or the scope its dispatch named."""

    number: str | None = None
    channel: Channel = Channel.phone
    # The scope the dispatch names, for the fleet's key; an org's own worker asks in its key's.
    org: str | None = None
    env: Env | None = None
    holder: str | None = None

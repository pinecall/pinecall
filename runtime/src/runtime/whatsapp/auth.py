"""WhatsApp's dependencies: the app that signed a body, its messages, an org's subscription, the threads."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from runtime.handles import TheSessions, TheSettings, TheVault
from runtime.kit.http import read_capped_body
from runtime.telephony import service as telephony
from runtime.telephony.auth import NumbersKey
from runtime.whatsapp.service import webhook


# Read in a transaction of its own, over before a message is read: each claim of a message is a
# transaction too, and a request that held one connection while it waited for another is how a pool
# runs dry under load.
async def find_box_app(sessions: TheSessions, vault: TheVault) -> webhook.MetaApp | None:
    """The box's Meta app, or None on a box that has none: an org's own app still subscribes there."""
    async with sessions.begin() as session:
        return await webhook.find_box_meta_app(session, vault)


TheBoxApp = Annotated[webhook.MetaApp | None, Depends(find_box_app)]


# The signature is checked on the bytes as they came. A body the box's app did not sign is read for
# the numbers it names and for nothing else, to find the orgs whose own app may have signed it.
async def read_signed_messages(
    request: Request, box: TheBoxApp, sessions: TheSessions, vault: TheVault
) -> list[webhook.Inbound]:
    """The messages of a body the box's app signed, or an org's own; 403 for a body neither did."""
    body = await read_capped_body(request, webhook.LONGEST_WEBHOOK, "a webhook's body")
    header = request.headers.get(webhook.SIGNATURE_HEADER)
    own: list[webhook.OwnApp] = []
    if box is None or not webhook.is_signed(box.app_secret, body, header):
        named = webhook.numbers_named_in(body)
        async with sessions.begin() as session:
            own = await telephony.list_own_meta_apps(session, vault, named) if named else []
    return webhook.read_signed(box, own, body, header)


SignedMessages = Annotated[list[webhook.Inbound], Depends(read_signed_messages)]


def subscription_of(actor: NumbersKey, vault: TheVault, settings: TheSettings) -> webhook.Subscription:
    """What the key's org types in its own Meta app so its numbers' messages come to this box."""
    return webhook.subscription_of(vault, actor.org, settings.base_url)


TheSubscription = Annotated[webhook.Subscription, Depends(subscription_of)]


def threads_of(connection: HTTPConnection) -> webhook.Threads:
    """The contacts' conversations, as the lifespan handed them in."""
    threads: webhook.Threads = connection.state.threads
    return threads


TheThreads = Annotated[webhook.Threads, Depends(threads_of)]

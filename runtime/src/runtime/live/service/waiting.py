"""The written messages that wait for an agent nobody holds: kept on the agent's log, taken off it, read back."""

from dataclasses import dataclass

from runtime.calls.log import Logs, Store
from runtime.enums import Env
from runtime.telephony.models import Route as RouteRow
from runtime.whatsapp import service as whatsapp
from runtime.wire.events import MessageTaken, MessageWaiting

WAITING = "message.waiting"
TAKEN = "message.taken"


@dataclass(frozen=True, slots=True)
class Waiting:
    """A message kept for an agent nobody held when it arrived."""

    agent: str
    env: Env
    inbound: whatsapp.Inbound
    received_at: float


async def keep_waiting(logs: Logs, store: Store, route: RouteRow, inbound: whatsapp.Inbound) -> Waiting:
    """Keep the message on the agent's log until somebody holds the agent."""
    now = store.clock()
    message = MessageWaiting.model_validate(
        {
            "channel": inbound.channel.value,
            "env": route.env.value,
            "number": inbound.number,
            "phone_number_id": inbound.phone_number_id,
            "from": inbound.wa_id,
            "name": inbound.name,
            "message_id": inbound.message_id,
            "text": inbound.text or "",
            "received_at": now,
        }
    )
    await logs.agent(route.agent).append(WAITING, message.dump())
    return Waiting(route.agent, route.env, inbound, now)


async def mark_taken(logs: Logs, waiting: Waiting, call: str | None) -> None:
    """The message off the queue: the call it went on, or none when its window closed."""
    await logs.agent(waiting.agent).append(TAKEN, MessageTaken(message_id=waiting.inbound.message_id, call=call).dump())


async def list_waiting(store: Store) -> list[Waiting]:
    """Every message still waiting, oldest first, read off every agent's log."""
    waiting: dict[str, Waiting] = {}
    after = 0
    while page := await store.list_across([WAITING, TAKEN], after=after):
        for row in page:
            entry = row.entry
            if entry.type == TAKEN:
                waiting.pop(str(entry.data.get("message_id")), None)
                continue
            message = MessageWaiting.model_validate(entry.data)
            inbound = whatsapp.Inbound(
                number=message.number,
                phone_number_id=message.phone_number_id,
                wa_id=message.from_,
                name=message.name,
                message_id=message.message_id,
                kind="text",
                text=message.text,
                channel=message.channel,
            )
            waiting[message.message_id] = Waiting(entry.agent, Env(message.env), inbound, message.received_at)
        after = page[-1].position
    return list(waiting.values())

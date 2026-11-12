"""Every statement on the telephony tables: an org's carrier accounts, the networks it asked for, and its numbers."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, exists, func, select, update

from runtime.enums import Channel, Env, RouteOrigin
from runtime.kit.repository import Repository
from runtime.telephony.models import Carrier, CarrierKind, CarrierNetwork, NetworkState, Route


@dataclass(frozen=True, slots=True)
class Numbered:
    """A number's row with the kind of the account it lives in."""

    route: Route
    # None for a number no account of the org holds: bought by the box, hooked, typed, or an
    # account since forgotten.
    carrier_kind: CarrierKind | None


@dataclass(frozen=True, slots=True)
class RouteToWrite:
    """A number's row as a hook leaves it: who answers it and where, how it came, and since when it is approved."""

    org: str
    number: str
    agent: str
    channel: Channel
    env: Env
    managed: bool = False
    account: str | None = None
    # A number hooked from networks of the org's own, which the operator approves.
    networks: tuple[str, ...] = ()
    origin: RouteOrigin = RouteOrigin.typed
    # The catalog carrier a number with no account comes through.
    via: str | None = None
    # None: written to wait, and no call to it opens until the operator approves it.
    approved_at: datetime | None = None


class CarrierRepository(Repository[Carrier]):
    """An org's carrier accounts, sealed."""

    model = Carrier

    async def list_of_org(self, org: str) -> Sequence[Carrier]:
        """The org's accounts, oldest first."""
        return await self.all(self.statement().where(Carrier.org == org).order_by(Carrier.set_at, Carrier.account))

    async def find(self, org: str, account: str) -> Carrier | None:
        """The org's account by its id."""
        return await self.one_or_none(self.statement().where(Carrier.org == org, Carrier.account == account))

    async def put(
        self, org: str, account: str, *, kind: CarrierKind, label: str, ciphertext: str, at: datetime
    ) -> Carrier:
        """Keep the account sealed, replacing what the org had under the id."""
        row = await self.find(org, account)
        if row is None:
            return await self.add(Carrier(org=org, account=account, kind=kind, label=label, ciphertext=ciphertext))
        return await self.update(row, kind=kind, label=label, ciphertext=ciphertext, set_at=at)

    async def delete_of(self, org: str, account: str) -> bool:
        """Forget the account; whether the org had it. Its numbers' rows name no account from then on."""
        return await self.change(delete(Carrier).where(Carrier.org == org, Carrier.account == account)) > 0

    async def list_every(self) -> Sequence[Carrier]:
        """Every org's accounts. Read box-wide by the caller."""
        return await self.all(self.statement().order_by(Carrier.org, Carrier.set_at))


class CarrierNetworkRepository(Repository[CarrierNetwork]):
    """The networks an org asks the box to open 5060 to, and the operator's answer to each."""

    model = CarrierNetwork

    async def list_of_source(self, org: str, source: str) -> Sequence[CarrierNetwork]:
        """The networks asked for one source, oldest first."""
        statement = self.statement().where(CarrierNetwork.org == org, CarrierNetwork.source == source)
        return await self.all(statement.order_by(CarrierNetwork.asked_at, CarrierNetwork.network))

    async def list_of_org(self, org: str) -> Sequence[CarrierNetwork]:
        """Every network the org asked for, oldest first."""
        return await self.all(
            self.statement().where(CarrierNetwork.org == org).order_by(CarrierNetwork.asked_at, CarrierNetwork.network)
        )

    async def list_in_state(self, state: NetworkState | None) -> Sequence[CarrierNetwork]:
        """Every network asked for on the box, or those in one state, oldest first. Read box-wide by the caller."""
        statement = self.statement()
        if state is not None:
            statement = statement.where(CarrierNetwork.state == state)
        return await self.all(statement.order_by(CarrierNetwork.asked_at, CarrierNetwork.id))

    async def ask(self, org: str, source: str, networks: Sequence[str]) -> Sequence[CarrierNetwork]:
        """Ask for these networks for the source, forgetting the ones it no longer names; its rows."""
        kept = {str(row.network): row for row in await self.list_of_source(org, source)}
        for network in networks:
            if network not in kept:
                await self.add(CarrierNetwork(org=org, source=source, network=network), flush=False)
        for network, row in kept.items():
            if network not in networks:
                await self.session.delete(row)
        await self.session.flush()
        return await self.list_of_source(org, source)

    async def find(self, ask_id: int) -> CarrierNetwork | None:
        """One ask by id, whatever org's. Read box-wide by the caller."""
        return await self.one_or_none(self.statement().where(CarrierNetwork.id == ask_id))

    async def decide(self, row: CarrierNetwork, state: NetworkState, by: str, at: datetime) -> CarrierNetwork:
        """Approve or refuse a network asked for."""
        return await self.update(row, state=state, decided_by=by, decided_at=at)


# Until 2026-11 the table was another domain's and the kind of a number's account was asked for one
# number at a time: every read here carries it, in the one join.
class RouteRepository(Repository[Route]):
    """Which agent answers a number, per org and env, and the account each number lives in."""

    model = Route

    async def list_of_org(
        self, org: str, env: Env, *, agent: str | None = None, channel: Channel | None = None
    ) -> Sequence[Numbered]:
        """The org's numbers in one env, oldest first; one agent's, or one channel's, when named."""
        statement = _with_carrier().where(Route.org == org, Route.env == env)
        if agent is not None:
            statement = statement.where(Route.agent == agent)
        if channel is not None:
            statement = statement.where(Route.channel == channel)
        return await self._read_with_carrier(statement.order_by(Route.added_at, Route.number))

    async def list_phones_of(self, org: str) -> Sequence[Numbered]:
        """The org's phone numbers in both envs, oldest first."""
        statement = _with_carrier().where(Route.org == org, Route.channel == Channel.phone)
        return await self._read_with_carrier(statement.order_by(Route.added_at, Route.number))

    async def list_of_agent(self, org: str, agent: str | None) -> Sequence[Route]:
        """The org's numbers in both envs, or those one of its agents answers, oldest first."""
        statement = self.statement().where(Route.org == org)
        if agent is not None:
            statement = statement.where(Route.agent == agent)
        return await self.all(statement.order_by(Route.added_at, Route.number))

    async def list_on_the_box(self) -> Sequence[Numbered]:
        """Every number of every org and env, by number. Read box-wide by the caller."""
        return await self._read_with_carrier(_with_carrier().order_by(Route.number, Route.channel, Route.added_at))

    async def find(self, org: str, number: str) -> Numbered | None:
        """The org's row at this number, whatever env it is in."""
        found = await self._read_with_carrier(_with_carrier().where(Route.org == org, Route.number == number))
        return found[0] if found else None

    # One org holds a number (routes_number_held_once), so a number reads one row at most.
    async def find_at(self, channel: Channel, number: str) -> Route | None:
        """The row a call dialled to this number takes, whatever org holds it. Read box-wide by the caller."""
        return await self.one_or_none(self.statement().where(Route.channel == channel, Route.number == number))

    # A number added again moves: its agent, channel, env and how it came are the newest said.
    async def put(self, written: RouteToWrite) -> Route:
        """Keep the row, replacing the one the org had at the number."""
        values = {
            "agent": written.agent,
            "channel": written.channel,
            "env": written.env,
            "managed": written.managed,
            "account": written.account,
            "networks": list(written.networks),
            "origin": written.origin,
            "via": written.via,
            "approved_at": written.approved_at,
        }
        row = await self.one_or_none(self.statement().where(Route.org == written.org, Route.number == written.number))
        if row is None:
            return await self.add(Route(org=written.org, number=written.number, **values))
        return await self.update(row, **values)

    async def note_call(self, org: str, number: str, *, at: datetime, unless_since: datetime) -> None:
        """Note that a call to the org's number reached the box at the moment, unless one was noted since the other."""
        await self.session.execute(
            update(Route)
            .where(
                Route.org == org,
                Route.number == number,
                (Route.last_call_at.is_(None)) | (Route.last_call_at < unless_since),
            )
            .values(last_call_at=at)
        )

    async def approve(self, org: str, number: str, *, by: str, at: datetime) -> bool:
        """Mark the org's waiting number approved; whether one waited."""
        statement = (
            update(Route)
            .where(Route.org == org, Route.number == number, Route.approved_at.is_(None))
            .values(approved_at=at, approved_by=by)
        )
        return await self.change(statement) > 0

    async def is_held_elsewhere(self, org: str, number: str) -> bool:
        """Whether another org holds the number on this box. Read box-wide by the caller."""
        statement = select(exists().where(Route.number == number, Route.org != org))
        return bool((await self.session.execute(statement)).scalar_one())

    async def list_numbers_of_others(self, org: str) -> set[str]:
        """Every number another org of this box holds. Read box-wide by the caller."""
        statement = select(Route.number).where(Route.org != org)
        return {str(number) for number in (await self.session.execute(statement)).scalars()}

    async def delete_of(self, org: str, number: str) -> bool:
        """Forget the org's row at the number; whether there was one."""
        return await self.change(delete(Route).where(Route.org == org, Route.number == number)) > 0

    async def list_of_agent_outside(self, agent: str, org: str) -> Sequence[Route]:
        """The numbers the agent answers in any org but this one, by number. Read box-wide by the caller."""
        return await self.all(self.statement().where(Route.agent == agent, Route.org != org).order_by(Route.number))

    # A number the target org already typed stays where it was: one row per number per org.
    async def move_with_agent(self, agent: str, org: str) -> list[str]:
        """Move the agent's numbers into the org; the numbers moved. Run box-wide by the caller."""
        theirs = select(Route.number).where(Route.org == org)
        moved = await self.session.execute(
            update(Route)
            .where(Route.agent == agent, Route.org != org, Route.number.not_in(theirs))
            .values(org=org)
            .returning(Route.number)
        )
        return sorted(str(number) for number in moved.scalars())

    async def count_managed(self, org: str, env: Env) -> int:
        """How many of the org's numbers in the env the box bought."""
        statement = (
            select(func.count()).select_from(Route).where(Route.org == org, Route.env == env, Route.managed.is_(True))
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def list_orgs_with_phones(self) -> list[str]:
        """Every org that answers at a phone number, by id. Read box-wide by the caller."""
        statement = select(Route.org).where(Route.channel == Channel.phone).distinct().order_by(Route.org)
        return [str(org) for org in (await self.session.execute(statement)).scalars()]

    async def _read_with_carrier(self, statement: Select[Route, CarrierKind]) -> list[Numbered]:
        rows = (await self.session.execute(statement)).all()
        return [Numbered(route, kind) for route, kind in rows]


# An outer join: the kind is NULL for a number no account of the org holds, whatever the column's type says.
def _with_carrier() -> Select[Route, CarrierKind]:
    return select(Route, Carrier.kind).outerjoin(
        Carrier, (Carrier.org == Route.org) & (Carrier.account == Route.account)
    )

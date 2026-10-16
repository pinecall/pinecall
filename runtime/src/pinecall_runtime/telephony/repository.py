"""The telephony tables: carriers, carrier_networks, dial_policy, dials, contact_consents."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on

from pinecall_runtime.channels.models import Route
from pinecall_runtime.enums import CarrierKind, ConsentKind, Env, NetworkState
from pinecall_runtime.kit.repository import Repository
from pinecall_runtime.kit.time import now
from pinecall_runtime.postgres import box_wide
from pinecall_runtime.telephony.models import Carrier, CarrierNetwork, ContactConsent, Dial, DialPolicy

A_MINUTE = timedelta(minutes=1)
A_DAY = timedelta(days=1)
# Two dials of one org cannot both take the last slot: the lock holds until the row is written.
LOCKED = text("SELECT pg_advisory_xact_lock(hashtext(:key))")


class CarrierRepository(Repository[Carrier]):
    """An org's carrier accounts, sealed."""

    model = Carrier

    async def of_org(self, org: str) -> Sequence[Carrier]:
        """The org's accounts, oldest first."""
        return await self.all(self.statement().where(Carrier.org == org).order_by(Carrier.set_at, Carrier.account))

    async def get(self, org: str, account: str) -> Carrier | None:
        """The org's account by its id."""
        return await self.one_or_none(self.statement().where(Carrier.org == org, Carrier.account == account))

    async def put(self, org: str, account: str, *, kind: CarrierKind, label: str, ciphertext: str) -> Carrier:
        """Keep the account sealed, replacing what the org had under the id."""
        row = await self.get(org, account)
        if row is None:
            return await self.add(Carrier(org=org, account=account, kind=kind, label=label, ciphertext=ciphertext))
        return await self.update(row, kind=kind, label=label, ciphertext=ciphertext, set_at=now())

    async def drop(self, org: str, account: str) -> bool:
        """Forget the account; whether the org had it."""
        row = await self.get(org, account)
        if row is None:
            return False
        await self.delete(row)
        return True

    async def every(self) -> Sequence[Carrier]:
        """Every org's accounts: the box's view, for the trunks of every Twilio account."""
        with box_wide():
            return await self.all(self.statement().order_by(Carrier.org, Carrier.set_at))


class CarrierNetworkRepository(Repository[CarrierNetwork]):
    """The networks an org asks the box to open 5060 to, and the operator's answer to each."""

    model = CarrierNetwork

    async def of_source(self, org: str, source: str) -> Sequence[CarrierNetwork]:
        """The networks asked for one source, oldest first."""
        statement = self.statement().where(CarrierNetwork.org == org, CarrierNetwork.source == source)
        return await self.all(statement.order_by(CarrierNetwork.asked_at, CarrierNetwork.network))

    async def of_org(self, org: str) -> Sequence[CarrierNetwork]:
        """Every network the org asked for, oldest first."""
        return await self.all(
            self.statement().where(CarrierNetwork.org == org).order_by(CarrierNetwork.asked_at, CarrierNetwork.network)
        )

    async def listed(self, state: NetworkState | None) -> Sequence[CarrierNetwork]:
        """Every network asked for on the box, or those in one state, oldest first."""
        with box_wide():
            statement = self.statement()
            if state is not None:
                statement = statement.where(CarrierNetwork.state == state)
            return await self.all(statement.order_by(CarrierNetwork.asked_at, CarrierNetwork.id))

    async def ask(self, org: str, source: str, networks: Sequence[str]) -> Sequence[CarrierNetwork]:
        """Ask for these networks for the source, forgetting the ones it no longer names; its rows."""
        kept = {str(row.network): row for row in await self.of_source(org, source)}
        for network in networks:
            if network not in kept:
                await self.add(CarrierNetwork(org=org, source=source, network=network), flush=False)
        for network, row in kept.items():
            if network not in networks:
                await self.session.delete(row)
        await self.session.flush()
        return await self.of_source(org, source)

    async def get(self, ask_id: int) -> CarrierNetwork | None:
        """One ask by id, whatever org's."""
        with box_wide():
            return await self.one_or_none(self.statement().where(CarrierNetwork.id == ask_id))

    async def decide(self, row: CarrierNetwork, state: NetworkState, by: str) -> CarrierNetwork:
        """Approve or refuse a network asked for."""
        return await self.update(row, state=state, decided_by=by, decided_at=now())


class DialPolicyRepository(Repository[DialPolicy]):
    """An org's dial guards, one row."""

    model = DialPolicy

    async def get(self, org: str) -> DialPolicy | None:
        """The org's row, or None when nobody set one."""
        return await self.one_or_none(self.statement().where(DialPolicy.org == org))

    async def put(
        self, org: str, *, dial_anywhere: bool, per_minute: int, per_day: int, max_duration_s: int
    ) -> DialPolicy:
        """Replace the org's guards whole."""
        row = await self.get(org)
        if row is None:
            return await self.add(
                DialPolicy(
                    org=org,
                    dial_anywhere=dial_anywhere,
                    per_minute=per_minute,
                    per_day=per_day,
                    max_duration_s=max_duration_s,
                )
            )
        return await self.update(
            row,
            dial_anywhere=dial_anywhere,
            per_minute=per_minute,
            per_day=per_day,
            max_duration_s=max_duration_s,
            set_at=now(),
        )


class DialRepository(Repository[Dial]):
    """The dial ledger: every outbound call asked for, placed or refused."""

    model = Dial

    async def refused(
        self, org: str, env: Env, agent: str, dialled: str, shown: str | None, asked_by: str, guard: str
    ) -> Dial:
        """A row for a dial a guard refused."""
        return await self.add(
            Dial(org=org, env=env, agent=agent, dialled=dialled, shown=shown, asked_by=asked_by, refused=guard)
        )

    async def was_placed(self, org: str, call: str, dialled: str) -> bool:
        """Whether this call's own first leg to the number was placed: its ledger row names the call."""
        statement = select(
            exists().where(Dial.org == org, Dial.call == call, Dial.dialled == dialled, Dial.refused.is_(None))
        )
        return bool((await self.session.execute(statement)).scalar_one())

    # Under the org's advisory lock: the counts and the row are one decision.
    async def paced(
        self,
        org: str,
        env: Env,
        agent: str,
        call: str,
        dialled: str,
        shown: str | None,
        asked_by: str,
        *,
        per_minute: int,
        per_day: int,
        per_number_day: int | None,
    ) -> tuple[str | None, int, int, int]:
        """Count the last day's dials, write the row placed or refused; the guard, and the counts."""
        await self.session.execute(LOCKED, {"key": f"dials:{org}"})
        at = now()
        since = at - A_DAY
        # A number's own count is of the calls placed to it, not the refusals: a refused dial rang nobody.
        counted = select(
            func.count().filter(Dial.at > at - A_MINUTE),
            func.count(),
            func.count().filter(Dial.dialled == dialled, Dial.refused.is_(None)),
        ).where(Dial.org == org, Dial.at > since)
        minute, day, number_day = (await self.session.execute(counted)).one()
        guard = None
        if minute >= per_minute:
            guard = "too_fast"
        elif day >= per_day:
            guard = "too_many"
        elif per_number_day is not None and number_day >= per_number_day:
            guard = "too_often"
        await self.add(
            Dial(
                org=org,
                env=env,
                agent=agent,
                call=None if guard else call,
                dialled=dialled,
                shown=shown,
                asked_by=asked_by,
                refused=guard,
                at=at,
            )
        )
        return guard, int(minute), int(day), int(number_day)

    async def to_number_since(self, number: str, since: datetime) -> Sequence[Dial]:
        """Every dial to the number since then, placed or refused, oldest first: the box's view."""
        with box_wide():
            return await self.all(self.statement().where(Dial.dialled == number, Dial.at >= since).order_by(Dial.at))


class ConsentRepository(Repository[ContactConsent]):
    """Facts about a number, never changed: the newest stands."""

    model = ContactConsent

    async def give(
        self,
        org: str,
        env: Env,
        number: str,
        *,
        kind: ConsentKind,
        source: str,
        given_by: str,
        text_: str | None,
        evidence: str | None,
        call: str | None,
    ) -> ContactConsent:
        """Write one fact about the number."""
        return await self.add(
            ContactConsent(
                org=org,
                env=env,
                number=number,
                kind=kind,
                source=source,
                text=text_,
                evidence=evidence,
                given_by=given_by,
                call=call,
            )
        )

    async def give_many(
        self, org: str, env: Env, numbers: Sequence[str], *, kind: ConsentKind, source: str, given_by: str
    ) -> None:
        """One fact for each number, in one flush."""
        await self.add_all(
            [
                ContactConsent(org=org, env=env, number=number, kind=kind, source=source, given_by=given_by)
                for number in numbers
            ]
        )

    async def history(self, org: str, env: Env, number: str) -> Sequence[ContactConsent]:
        """Every fact about the number, newest first."""
        statement = self.statement().where(
            ContactConsent.org == org, ContactConsent.env == env, ContactConsent.number == number
        )
        return await self.all(statement.order_by(ContactConsent.given_at.desc(), ContactConsent.id.desc()))

    async def newest(self, org: str, env: Env, number: str) -> ContactConsent | None:
        """The newest fact about the number."""
        statement = self.statement().where(
            ContactConsent.org == org, ContactConsent.env == env, ContactConsent.number == number
        )
        return await self.one_or_none(
            statement.order_by(ContactConsent.given_at.desc(), ContactConsent.id.desc()).limit(1)
        )

    # The numbers whose newest row is an opt-out, newest row first, after the row id a page ended on.
    async def opted_out(
        self, org: str, env: Env, *, after: int | None, limit: int
    ) -> list[tuple[int, str, datetime, str, str]]:
        """A page of the do-not-call list: id, number, since, source, by."""
        newest = (
            select(
                ContactConsent.id,
                ContactConsent.number,
                ContactConsent.kind,
                ContactConsent.given_at,
                ContactConsent.source,
                ContactConsent.given_by,
            )
            .where(ContactConsent.org == org, ContactConsent.env == env)
            .ext(distinct_on(ContactConsent.number))
            .order_by(ContactConsent.number, ContactConsent.given_at.desc(), ContactConsent.id.desc())
            .subquery("newest")
        )
        statement = select(newest.c.id, newest.c.number, newest.c.given_at, newest.c.source, newest.c.given_by).where(
            newest.c.kind == ConsentKind.opt_out
        )
        if after is not None:
            statement = statement.where(newest.c.id < after)
        rows = (await self.session.execute(statement.order_by(newest.c.id.desc()).limit(limit))).all()
        return [(int(id_), str(number), given_at, str(source), str(by)) for id_, number, given_at, source, by in rows]

    async def opted_out_on(self, call: str) -> bool:
        """Whether a number went on the do-not-call list on this call."""
        statement = select(exists().where(ContactConsent.call == call, ContactConsent.kind == ConsentKind.opt_out))
        return bool((await self.session.execute(statement)).scalar_one())


class RouteCarrierRepository(Repository[Route]):
    """Each route with the kind of the carrier account it lives in."""

    model = Route

    async def on_the_box(self) -> list[tuple[Route, CarrierKind | None]]:
        """Every route of every org and env, by number, with the kind of the carrier it lives in."""
        statement = (
            select(Route, Carrier.kind)
            .outerjoin(Carrier, (Carrier.org == Route.org) & (Carrier.account == Route.account))
            .order_by(Route.number, Route.channel, Route.added_at)
        )
        return [(route, kind) for route, kind in (await self.session.execute(statement)).all()]

    async def carrier_kind_of(self, route: Route) -> str | None:
        """The kind of the org's account the number lives in, or None."""
        if route.account is None:
            return None
        statement = select(Carrier.kind).where(Carrier.org == route.org, Carrier.account == route.account)
        kind = (await self.session.execute(statement)).scalar_one_or_none()
        return None if kind is None else str(kind)

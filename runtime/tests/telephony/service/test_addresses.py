"""An address of the platform's own domain given to an org's agent: its mailbox made, kept, routed, let go."""

import json

import httpx
import pytest

from runtime.accounts import service as accounts
from runtime.enums import Channel, Env
from runtime.exceptions import Conflict, ServiceUnavailable
from runtime.telephony.repository import CarrierRepository, RouteRepository
from runtime.telephony.service import addresses, numbers
from tests.telephony.conftest import Line

DOMAIN = "agents.example"
HOST = addresses.MailHost(url="https://mailhost.example/admin-api", key="the key", domain=DOMAIN, server="mail.example")


class MailHost:
    """The platform's mail host as its admin API answers: mailboxes made and removed, and what it was asked."""

    def __init__(self, *, taken: bool = False) -> None:
        self.taken = taken
        self.asked: list[tuple[str, str, dict[str, str]]] = []

    def answer(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, str] = json.loads(request.content) if request.content else {}
        self.asked.append((request.method, request.url.path, body))
        assert request.headers["Authorization"] == "Bearer the key"
        if request.method == "POST":
            if self.taken:
                return httpx.Response(409, json={"code": "mailbox_exists", "detail": "taken"})
            return httpx.Response(201, json={"address": f"{body['local']}@{DOMAIN}", "password": "made here"})
        return httpx.Response(204)


async def _given(line: Line, host: MailHost, local: str = "avisos", app: str | None = "front-desk-app") -> str:
    wanted = addresses.AddressWanted(line.scope(Env.sandbox), local, "recepcion", app, "Avisos")
    async with httpx.AsyncClient(transport=httpx.MockTransport(host.answer)) as http, line.sessions.begin() as session:
        plan = await addresses.give_address(session, line.vault, http, line.livekits, line.names, HOST, wanted)
    assert plan.route.number is not None
    return plan.route.number


async def test_an_address_is_made_on_the_host_under_the_orgs_slug_kept_and_routed_as_the_boxs(line: Line) -> None:
    host = MailHost()
    address = await _given(line, host)
    async with line.sessions() as session:
        slug = (await accounts.get_org(session, line.org)).slug
        route = await RouteRepository(session).find(line.org, address, Channel.email)
        kept = await CarrierRepository(session).find(line.org, address)
    assert address == f"avisos.{slug}@{DOMAIN}"
    assert host.asked == [
        ("POST", f"/admin-api/v1/domains/{DOMAIN}/mailboxes", {"local": f"avisos.{slug}", "name": "Avisos"})
    ]
    assert route is not None and (route.route.managed, route.route.app, route.route.agent) == (
        True,
        "front-desk-app",
        "recepcion",
    )
    assert kept is not None and kept.kind == "email"


async def test_an_address_the_host_has_already_is_refused_and_nothing_is_kept(line: Line) -> None:
    with pytest.raises(Conflict, match="is taken"):
        await _given(line, MailHost(taken=True))
    async with line.sessions() as session:
        assert list(await RouteRepository(session).list_of_org(line.org, Env.sandbox)) == []


async def test_a_platform_with_no_mail_host_gives_no_address(line: Line) -> None:
    wanted = addresses.AddressWanted(line.scope(Env.sandbox), "avisos", "recepcion")
    with pytest.raises(ServiceUnavailable, match="gives out no addresses"):
        async with line.sessions.begin() as session:
            await addresses.give_address(session, line.vault, line.http, line.livekits, line.names, None, wanted)


async def test_letting_a_made_address_go_removes_its_mailbox_and_its_account(line: Line) -> None:
    host = MailHost()
    address = await _given(line, host, app=None)
    async with line.sessions() as session:
        route = await RouteRepository(session).find(line.org, address, Channel.email)
    assert route is not None
    async with httpx.AsyncClient(transport=httpx.MockTransport(host.answer)) as http, line.sessions.begin() as session:
        await numbers.let_go(session, line.vault, http, line.livekits, line.names, route.route, HOST)
    assert host.asked[-1][:2] == ("DELETE", f"/admin-api/v1/domains/{DOMAIN}/mailboxes/{address.split('@')[0]}")
    async with line.sessions() as session:
        assert await CarrierRepository(session).find(line.org, address) is None
        assert await RouteRepository(session).find(line.org, address, Channel.email) is None

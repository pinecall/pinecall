"""An app that asks to act as a person: registered here with nothing kept, or read from the document its id names."""

import os

import httpx
import pytest

from runtime.kit import dns
from runtime.kit.crypto import Vault
from runtime.signin.service.clients import Clients, InvalidClient, InvalidRedirect, check_redirect, host_of
from tests.fakes.internet import A_PUBLIC_ADDRESS, Internet

THE_DOCUMENT = "https://app.example.test/oauth/client.json"


async def on_the_internet(url: str) -> dns.Resolved:
    """A name a test serves, said to resolve onto the internet."""
    return dns.Resolved(httpx.URL(url).host, (A_PUBLIC_ADDRESS,))


async def inside(url: str) -> dns.Resolved:
    """A name that resolves to the box's own network."""
    return dns.Resolved(httpx.URL(url).host, (dns.resolve("127.0.0.1")[0],))


def the_clients(internet: Internet, resolve: dns.ResolveUrl = on_the_internet) -> Clients:
    """The clients of a gateway whose requests go out through the suite's internet."""
    return Clients(httpx.AsyncClient(transport=internet), Vault(os.environ["PINECALL_VAULT_KEY"]), resolve)


async def test_a_registration_is_its_own_id_and_is_read_back_from_it(internet: Internet) -> None:
    """What an app registered comes back from the id alone: nothing was kept."""
    clients = the_clients(internet)
    registered = clients.register("Claude", ["https://claude.ai/api/mcp/auth_callback"])
    found = await clients.get_client(registered.id)
    assert (found.name, found.redirect_uris) == ("Claude", ("https://claude.ai/api/mcp/auth_callback",))


async def test_an_id_this_gateway_never_sealed_names_no_app(internet: Internet) -> None:
    """A registration made up, or cut short, is refused as OAuth names it."""
    clients = the_clients(internet)
    registered = clients.register("An editor", ["http://127.0.0.1:33418/callback"])
    for wrong in (registered.id[:-6], "pcc_made-up", "whoever"):
        with pytest.raises(InvalidClient) as refused:
            await clients.get_client(wrong)
        assert refused.value.error == "invalid_client"


@pytest.mark.parametrize(
    "uri",
    [
        "javascript:alert(1)",
        "data:text/html,hello",
        "http://evil.example/callback",
        "https://app.example/callback#fragment",
        "https://app.example/call back",
        "no-scheme",
    ],
)
def test_an_address_no_approval_may_be_sent_to_is_never_registered(uri: str, internet: Internet) -> None:
    """What a browser would run, plain http off the person's machine, a fragment, a space: refused."""
    with pytest.raises(InvalidRedirect):
        the_clients(internet).register("An app", [uri])


def test_an_app_registers_at_least_one_address_and_at_most_ten(internet: Internet) -> None:
    """None and eleven are both refused."""
    clients = the_clients(internet)
    for wrong in ([], [f"https://app.example/{at}" for at in range(11)]):
        with pytest.raises(InvalidRedirect):
            clients.register("An app", wrong)


def test_an_approval_goes_only_where_the_app_registered(internet: Internet) -> None:
    """The exact address; on the person's own machine, any port of the one registered; nowhere else."""
    clients = the_clients(internet)
    web = clients.register("A site", ["https://app.example/callback"])
    local = clients.register("An editor", ["http://127.0.0.1:33418/callback", "cursor://anysphere.cursor-mcp/oauth"])
    assert check_redirect(web, "https://app.example/callback") == "https://app.example/callback"
    assert check_redirect(local, "http://127.0.0.1:51234/callback") == "http://127.0.0.1:51234/callback"
    assert check_redirect(local, "cursor://anysphere.cursor-mcp/oauth") == "cursor://anysphere.cursor-mcp/oauth"
    for client, wrong in (
        (web, "https://app.example/callback/other"),
        (web, "https://evil.example/callback"),
        (web, "http://127.0.0.1:51234/callback"),
        (local, "http://127.0.0.1:51234/another"),
        (local, "http://localhost:51234/callback"),
    ):
        with pytest.raises(InvalidRedirect):
            check_redirect(client, wrong)


def test_where_an_approval_lands_is_said_by_its_host_or_the_apps_own_scheme() -> None:
    """What the person approving reads."""
    assert host_of("https://claude.ai/api/mcp/auth_callback") == "claude.ai"
    assert host_of("http://127.0.0.1:33418/callback") == "127.0.0.1"
    assert host_of("cursor://anysphere.cursor-mcp/oauth") == "anysphere.cursor-mcp"
    assert host_of("com.example.app:/oauth") == "com.example.app:"


async def test_an_app_is_read_from_the_document_its_id_is_the_address_of(internet: Internet) -> None:
    """A client metadata document that names its own address is the app, asked at the address checked."""
    document = {"client_id": THE_DOCUMENT, "client_name": "ChatGPT", "redirect_uris": ["https://chatgpt.com/cb"]}
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json=document)

    # The request goes to the address the name was checked to resolve to, the name riding its Host.
    with internet.serving(str(A_PUBLIC_ADDRESS), answer):
        found = await the_clients(internet).get_client(THE_DOCUMENT)
    assert (found.id, found.name, found.redirect_uris) == (THE_DOCUMENT, "ChatGPT", ("https://chatgpt.com/cb",))
    assert asked == [f"https://{A_PUBLIC_ADDRESS}/oauth/client.json"]


@pytest.mark.parametrize(
    "document",
    [
        {"client_id": "https://another.example/client.json", "redirect_uris": ["https://chatgpt.com/cb"]},
        {"client_id": THE_DOCUMENT, "redirect_uris": []},
        {"client_id": THE_DOCUMENT, "redirect_uris": ["javascript:alert(1)"]},
        ["not", "a", "document"],
    ],
)
async def test_a_document_that_is_not_its_own_or_lists_nowhere_to_go_is_refused(
    document: object, internet: Internet
) -> None:
    """A document naming another address as its id, or no address an approval can be sent to."""
    with (
        internet.serving(str(A_PUBLIC_ADDRESS), lambda _request: httpx.Response(200, json=document)),
        pytest.raises((InvalidClient, InvalidRedirect)),
    ):
        await the_clients(internet).get_client(THE_DOCUMENT)


async def test_a_document_inside_the_box_is_never_asked(internet: Internet) -> None:
    """A client_id that resolves to the box's own network is refused before any request leaves."""
    with pytest.raises(InvalidClient):
        await the_clients(internet, inside).get_client("https://metadata.internal.test/client.json")
    with pytest.raises(InvalidClient):
        await the_clients(internet).get_client("https://app.example.test")

"""The gateway's doors from one base URL, and a request signed by a header, never by its URL."""

from pinecall._endpoints import agent_log_url, apps_url, call_log_url, lookup_url, signed


def test_the_socket_takes_the_bases_scheme_as_a_websockets() -> None:
    assert apps_url("https://cloud.pinecall.io") == "wss://cloud.pinecall.io/v1/apps"
    assert apps_url("http://127.0.0.1:8180/") == "ws://127.0.0.1:8180/v1/apps"


def test_a_door_under_a_base_with_a_path_keeps_it_and_quotes_what_it_names() -> None:
    assert (
        call_log_url("https://box.example/pc", "CA 1")
        == "https://box.example/pc/v1/calls/CA%201/events"
    )
    assert (
        agent_log_url("https://box.example", "clinica-norte")
        == "https://box.example/v1/agents/clinica-norte/calls"
    )
    assert lookup_url("wss://box.example", "CA_1") == "https://box.example/v1/calls/CA_1/lookup"


def test_the_key_is_a_bearer_and_the_world_a_header_of_its_own() -> None:
    assert signed("pk_1", "production") == {
        "authorization": "Bearer pk_1",
        "pinecall-env": "production",
    }
    assert signed("", None) == {}

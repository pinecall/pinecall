"""A server's files: Caddy's routes, sites and pages, LiveKit's own pair or the operator's, SIP's ports, the wheel."""

from pathlib import Path

from runtime.cli.setup import server as server_
from runtime.cli.setup import server_files
from runtime.cli.setup.files import write_shipped

NAME = "voice.example.com"
THEIRS = server_.TheirLiveKit("wss://acme.livekit.cloud", "APIacme", "their-secret")


def written(tmp_path: Path, server: server_.Server) -> dict[str, str]:
    env = write_shipped(tmp_path)
    values = env.set(**server_.settings_of(server, env.read()))
    server_files.write_files(tmp_path, server, values, None)
    return values


def test_a_server_draws_its_own_livekit_pair_and_keeps_the_gateway_on_loopback(tmp_path: Path) -> None:
    """Never the laptop's development pair; LiveKit's events reach the gateway on loopback; Caddy is the door."""
    values = written(tmp_path, server_.Server(NAME))
    assert values["PINECALL_DOMAIN"] == NAME
    assert values["LIVEKIT_API_KEY"] == server_.LIVEKIT_KEY
    assert values["LIVEKIT_API_SECRET"] != "a-laptop-only-livekit-secret-0123456789"
    assert "PINECALL_GATEWAY_LISTEN" not in values and "LIVEKIT_PUBLIC_URL" not in values
    # LiveKit's config is said in the compose file from the env file's values: no file of its own holds the secret.
    compose = (tmp_path / "server.yaml").read_text()
    assert "${LIVEKIT_API_KEY}: ${LIVEKIT_API_SECRET}" in compose
    assert "http://127.0.0.1:8079/v1/livekit/webhook" in compose and "use_external_ip: true" in compose
    assert not (tmp_path / "livekit.server.yaml").exists()
    caddy = (tmp_path / "Caddyfile").read_text()
    assert caddy.startswith(f"{NAME} {{") and "/rtc" in caddy
    # Either gateway, whichever is up, for the name and, on a port of loopback, for what runs here.
    assert caddy.count("reverse_proxy 127.0.0.1:8080 127.0.0.1:8081 {") == 2
    assert "http://:8079 {\n\tbind 127.0.0.1\n" in caddy and "health_uri /.well-known/pinecall" in caddy


def test_a_second_run_keeps_the_pair(tmp_path: Path) -> None:
    """Run again, the server keeps the secret LiveKit and its rooms were signed with."""
    first = written(tmp_path, server_.Server(NAME))
    again = written(tmp_path, server_.Server(NAME))
    assert again["LIVEKIT_API_SECRET"] == first["LIVEKIT_API_SECRET"]


def test_their_livekit_is_the_runtimes_and_the_browsers(tmp_path: Path) -> None:
    """With the operator's own LiveKit, Caddy carries no /rtc and every setting names theirs."""
    values = written(tmp_path, server_.Server(NAME, THEIRS))
    assert values["LIVEKIT_URL"] == values["LIVEKIT_PUBLIC_URL"] == THEIRS.url
    assert values["LIVEKIT_API_KEY"] == THEIRS.key and values["LIVEKIT_API_SECRET"] == THEIRS.secret
    assert "/rtc" not in (tmp_path / "Caddyfile").read_text()
    assert server_.from_the_env(values) == server_.Server(NAME, THEIRS)


def test_the_image_installs_this_release_or_the_wheel_given(tmp_path: Path) -> None:
    """From PyPI at this package's version, or the wheel `--from` names, copied beside the Dockerfile."""
    assert server_.image_of(None)["PINECALL_RUNTIME_SPEC"].startswith("pinecall-runtime[voice]==")
    wheel = tmp_path / "runtime-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    values = write_shipped(tmp_path).set(**server_.settings_of(server_.Server(NAME), {}))
    server_files.write_files(tmp_path, server_.Server(NAME), values, wheel)
    assert (tmp_path / "runtime" / "wheels" / wheel.name).read_bytes() == b"wheel"
    assert server_.image_of(wheel)["PINECALL_RUNTIME_SPEC"] == f"/wheels/{wheel.name}[voice]"


def test_the_phones_ports_are_the_env_files(tmp_path: Path) -> None:
    """Twenty RTP ports unless the env file names a range: a call takes one, and the firewall opens the same."""
    written(tmp_path, server_.Server(NAME, phone=True))
    assert "rtp_port: ${PINECALL_SIP_RTP_PORTS:-10000-10019}" in (tmp_path / "server.yaml").read_text()


def test_the_configs_a_server_wrote_with_a_secret_in_them_are_removed(tmp_path: Path) -> None:
    """LiveKit's and SIP's files of before held LiveKit's secret: a run takes them off the machine."""
    for name in server_files.GONE:
        (tmp_path / name).write_text("keys:\n  pinecall: an-old-secret\n")
    written(tmp_path, server_.Server(NAME, phone=True))
    assert not any((tmp_path / name).exists() for name in server_files.GONE)


def test_a_servers_passwords_are_drawn_once_and_kept(tmp_path: Path) -> None:
    """Redis's and the gateways' role's: drawn the first time, the same on every run after, in their URLs."""
    first = written(tmp_path, server_.Server(NAME))
    password = first[server_.REDIS_PASSWORD]
    assert len(password) == 48 and first["PINECALL_REDIS_URL"] == f"redis://:{password}@127.0.0.1:56380/0"
    assert first["PINECALL_DB_APP_ROLE"] == server_.APP_ROLE
    assert first[server_.APP_URL].startswith(f"postgresql://{server_.APP_ROLE}:")
    assert first[server_.APP_URL].endswith("@127.0.0.1:55433/pinecall")
    again = written(tmp_path, server_.Server(NAME))
    drawn = server_.passwords_of({})
    assert {name: again[name] for name in drawn} == {name: first[name] for name in drawn}


def test_caddy_serves_the_operators_sites_and_the_apps_pages(tmp_path: Path) -> None:
    """sites/ is the operator's and survives every run; a page's name gets its certificate once the gateway knows it."""
    written(tmp_path, server_.Server(NAME))
    caddy = (tmp_path / "Caddyfile").read_text()
    assert "import sites/*.caddy" in caddy and "on_demand" not in caddy
    theirs = tmp_path / "sites" / "billing.caddy"
    theirs.write_text("billing.example.com {\n\treverse_proxy 127.0.0.1:8095\n}\n")
    env = write_shipped(tmp_path)
    values = env.set(PINECALL_PAGES_DOMAIN="app.example.com")
    server_files.write_files(tmp_path, server_.Server(NAME), values, None)
    caddy = (tmp_path / "Caddyfile").read_text()
    assert caddy.startswith("{\n\ton_demand_tls {\n\t\task http://127.0.0.1:8079/v1/pages/known\n")
    assert caddy.count("reverse_proxy 127.0.0.1:8080 127.0.0.1:8081 {") == 3
    assert "*.app.example.com {\n\ttls {\n\t\ton_demand\n" in caddy
    assert theirs.read_text().startswith("billing.example.com")

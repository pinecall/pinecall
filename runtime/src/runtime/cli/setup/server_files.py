"""The files a server keeps: its compose file, Caddy's, the image's Dockerfile."""

from pathlib import Path
from shutil import copyfile

from runtime.cli.setup.files import find_shipped
from runtime.cli.setup.server import Server

# The operator's own sites stand beside the runtime's: setup writes this file whole on every run and
# never a file of sites/.
CADDYFILE = """{options}{name} {{
{livekit}{gateways}}}

# The gateways for what runs on this machine: the workers' knocks, LiveKit's events, a service of
# the operator's own. On loopback alone, and by whatever name the caller says: one that asks as the
# public name, as a service that also runs in a cluster does, is answered as any other (a site
# named 127.0.0.1 answered it nothing).
http://:8079 {{
	bind 127.0.0.1
{gateways}}}
{pages}
import sites/*.caddy
"""
# Either gateway, whichever is up: one that refuses a connection is passed over at once and tried
# again within seconds, so a gateway starting again loses no request (a server's two are started
# one after the other).
GATEWAYS = """	reverse_proxy 127.0.0.1:8080 127.0.0.1:8081 {
		lb_policy round_robin
		lb_try_duration 30s
		lb_try_interval 250ms
		health_uri /.well-known/pinecall
		health_interval 2s
		fail_duration 5s
	}
"""
# An app's page is served at its own name under the pages' domain, by the gateway. No certificate
# covers names nobody knows yet, so each is asked for on the first visit, once the gateway has said
# the name is a page of an app that runs: nobody makes this machine ask for a certificate by typing
# a name.
ON_DEMAND = """{
	on_demand_tls {
		ask http://127.0.0.1:8079/v1/pages/known
	}
}

"""
PAGES_SITE = """
*.{pages} {{
	tls {{
		on_demand
	}}
{gateways}}}
"""
# The browser's LiveKit is reached under the name: /rtc is LiveKit's signal path.
LIVEKIT_ROUTE = "\t@livekit path /rtc /rtc/*\n\treverse_proxy @livekit 127.0.0.1:7880\n"

# LiveKit's and SIP's configs, which held LiveKit's secret and were read as root: said in server.yaml
# from the env file's values since 2026-11-23, and taken off a machine that still has them.
GONE = ("livekit.server.yaml", "sip.server.yaml")


def write_files(where: Path, server: Server, values: dict[str, str], wheel: Path | None) -> None:
    """The server's compose, its image's Dockerfile and wheel, and Caddy's file."""
    dockerfile = where / "runtime" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_text(find_shipped("runtime/Dockerfile").read_text(encoding="utf-8"), encoding="utf-8")
    wheels = where / "runtime" / "wheels"
    wheels.mkdir(exist_ok=True)
    for old in wheels.iterdir():
        old.unlink()
    if wheel is not None:
        copyfile(wheel, wheels / wheel.name)
    write_configs(where, server, values)


# What the env file and this release say now, so `local up` writes them too: the compose file is the
# package's, the pages' domain a site of Caddy's.
def write_configs(where: Path, server: Server, values: dict[str, str]) -> None:
    """The server's compose file and Caddy's; the configs it once wrote with a secret in them removed."""
    (where / "server.yaml").write_text(find_shipped("server.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (where / "sites").mkdir(exist_ok=True)
    (where / "Caddyfile").write_text(caddyfile_of(server, values.get("PINECALL_PAGES_DOMAIN")), encoding="utf-8")
    for name in GONE:
        (where / name).unlink(missing_ok=True)


def caddyfile_of(server: Server, pages: str | None) -> str:
    """Caddy's file: the server's name, LiveKit's path under it, the pages' names if any, the operator's sites."""
    route = LIVEKIT_ROUTE if server.livekit is None else ""
    return CADDYFILE.format(
        options=ON_DEMAND if pages else "",
        name=server.name,
        livekit=route,
        gateways=GATEWAYS,
        pages=PAGES_SITE.format(pages=pages, gateways=GATEWAYS) if pages else "",
    )

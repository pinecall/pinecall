"""The files a server keeps beside its compose file: Caddy's, LiveKit's and SIP's configs, the image's Dockerfile."""

from pathlib import Path
from shutil import copyfile

from runtime.cli.setup.files import find_shipped
from runtime.cli.setup.server import Server

FILES = ("server.yaml", "runtime/Dockerfile")
# The env file's name for the range of ports SIP's audio uses; it stays as the operator wrote it.
RTP_PORTS = "PINECALL_SIP_RTP_PORTS"
# Twenty ports, a call each: what a server of four seats an environment needs twice over.
RTP_PORTS_UNLESS_SAID = "10000-10019"


# The operator's own sites stand beside the runtime's: setup writes this file whole on every run and
# never a file of sites/.
CADDYFILE = """{options}{name} {{
{livekit}	reverse_proxy 127.0.0.1:8080
}}
{pages}
import sites/*.caddy
"""
# An app's page is served at its own name under the pages' domain, by the gateway. No certificate
# covers names nobody knows yet, so each is asked for on the first visit, once the gateway has said
# the name is a page of an app that runs: nobody makes this machine ask for a certificate by typing
# a name.
ON_DEMAND = """{
	on_demand_tls {
		ask http://127.0.0.1:8080/v1/pages/known
	}
}

"""
PAGES_SITE = """
*.{pages} {{
	tls {{
		on_demand
	}}
	reverse_proxy 127.0.0.1:8080
}}
"""
# The browser's LiveKit is reached under the name: /rtc is LiveKit's signal path.
LIVEKIT_ROUTE = "\t@livekit path /rtc /rtc/*\n\treverse_proxy @livekit 127.0.0.1:7880\n"

LIVEKIT_CONFIG = """# LiveKit as a server: its media on the machine's public address, the pair drawn for this machine,
# its events to the gateway on loopback (one LiveKit serves both environments here).
port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: true
redis:
  address: 127.0.0.1:56380
keys:
  {key}: {secret}
webhook:
  api_key: {key}
  urls:
    - http://127.0.0.1:8080/v1/livekit/webhook
logging:
  level: info
"""

SIP_CONFIG = """# LiveKit's SIP as a server: calls to this machine's :5060, their audio on its RTP ports, a call each.
api_key: {key}
api_secret: {secret}
ws_url: ws://127.0.0.1:7880
redis:
  address: 127.0.0.1:56380
sip_port: 5060
rtp_port: {rtp}
use_external_ip: true
logging:
  level: info
"""


# A service by the file it reads once, as it starts: one whose file changed under it is started again.
READ_BY = {"livekit.server.yaml": "livekit-server", "sip.server.yaml": "sip-server"}


def write_files(where: Path, server: Server, values: dict[str, str], wheel: Path | None) -> tuple[str, ...]:
    """The server's compose, its image's Dockerfile and wheel, and its configs; the services to start again."""
    for name in FILES:
        target = where / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(find_shipped(name).read_text(encoding="utf-8"), encoding="utf-8")
    wheels = where / "runtime" / "wheels"
    wheels.mkdir(exist_ok=True)
    for old in wheels.iterdir():
        old.unlink()
    if wheel is not None:
        copyfile(wheel, wheels / wheel.name)
    return write_configs(where, server, values)


# Each is what the env file says now, so `local up` writes them too: the pages' domain is a site of
# Caddy's, the range of SIP's audio a line of its config.
def write_configs(where: Path, server: Server, values: dict[str, str]) -> tuple[str, ...]:
    """Caddy's file and LiveKit's and SIP's configs; the services whose config changed under them."""
    (where / "sites").mkdir(exist_ok=True)
    (where / "Caddyfile").write_text(caddyfile_of(server, values.get("PINECALL_PAGES_DOMAIN")), encoding="utf-8")
    said = {
        "key": values["LIVEKIT_API_KEY"],
        "secret": values["LIVEKIT_API_SECRET"],
        "rtp": values.get(RTP_PORTS) or RTP_PORTS_UNLESS_SAID,
    }
    changed: list[str] = []
    for name, text in (("livekit.server.yaml", LIVEKIT_CONFIG), ("sip.server.yaml", SIP_CONFIG)):
        target = where / name
        before = target.read_text(encoding="utf-8") if target.is_file() else None
        target.touch(mode=0o600)
        target.write_text(text.format(**said), encoding="utf-8")
        target.chmod(0o600)
        # A file written for the first time is read by the service made with it.
        if before is not None and before != text.format(**said):
            changed.append(READ_BY[name])
    return tuple(changed)


def caddyfile_of(server: Server, pages: str | None) -> str:
    """Caddy's file: the server's name, LiveKit's path under it, the pages' names if any, the operator's sites."""
    route = LIVEKIT_ROUTE if server.livekit is None else ""
    return CADDYFILE.format(
        options=ON_DEMAND if pages else "",
        name=server.name,
        livekit=route,
        pages=PAGES_SITE.format(pages=pages) if pages else "",
    )

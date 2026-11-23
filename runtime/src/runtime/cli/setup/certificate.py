"""A server's certificate, asked for again: Caddy started again when the name points here and it holds none."""

import socket
import ssl
from collections.abc import Callable
from pathlib import Path

from runtime.cli.setup.compose import Compose
from runtime.cli.setup.server import (
    UP_FAILED,
    Here,
    Resolve,
    Server,
    compose_files,
    image_of,
    resolve_ipv4,
    this_machines_address,
)

# Whether this machine's Caddy answers a name with a certificate a client trusts; a test hands in its own.
type Holds = Callable[[str], bool]


def holds_certificate(name: str) -> bool:
    """Whether Caddy, asked on this machine for the name, answers with a certificate a client trusts."""
    try:
        with (
            socket.create_connection(("127.0.0.1", 443), timeout=5) as plain,
            ssl.create_default_context().wrap_socket(plain, server_hostname=name),
        ):
            return True
    except OSError:
        return False


# A server set up before its name pointed at it (`--unpointed`) has a Caddy that asked, was refused,
# and waits longer after each refusal: ten minutes between tries after half an hour, which is how
# long a name that had just moved went unanswered on 2026-11-23. Started again, Caddy asks at once,
# for every name it serves, the operator's own sites among them. It is started again only where
# that costs nothing: it holds no certificate for the name, so it answers nobody at it, and the
# name points here, so the asking can succeed.
def ask_again(
    where: Path,
    server: Server,
    values: dict[str, str],
    *,
    holds: Holds = holds_certificate,
    resolve: Resolve = resolve_ipv4,
    here: Here = this_machines_address,
) -> bool:
    """Caddy started again when the name points here and it holds no certificate for it; whether it was."""
    if holds(server.name):
        return False
    try:
        found = resolve(server.name)
    except socket.gaierror:
        return False
    if here() not in found:
        return False
    running = Compose(compose_files(where), ("server",), {**values, **image_of(None, server.image)})
    running.run("--progress", "quiet", "restart", "caddy", failed=UP_FAILED)
    return True

"""The name a release's process runs under, and what is read back off it."""

import hashlib
import re

from runtime.enums import Env

STAMP = 8
# <name>-r<release>-<stamp>: the release is read back off it, so a report names nothing else.
A_HOST = re.compile(rf"^(?P<name>[a-z0-9-]+)-r(?P<release>[1-9][0-9]*)-[0-9a-f]{{{STAMP}}}$")


# What the process calls its machine, which is what the gateway's list of processes shows, and the
# name of its container on a machine every org's apps share: the stamp is of the org, the env and
# the app too, so two orgs' apps of one name and one source never meet, and of the org's secrets,
# so a changed secret is a new host.
def host_of(org: str, env: Env, name: str, release: int, sha256: str, secrets: str) -> str:
    """The host name one release of the app runs under, with the org's secrets as they are."""
    stamped = f"{org}:{env.value}:{name}:{release}:{sha256}:{secrets}"
    return f"{name}-r{release}-{hashlib.sha256(stamped.encode()).hexdigest()[:STAMP]}"


def is_host_of(name: str, host: str) -> bool:
    """Whether the host is one a release of the app runs under, whichever release."""
    named = A_HOST.match(host)
    return named is not None and named["name"] == name


def release_of(host: str) -> int | None:
    """The release a host runs, read off its name; None for a name that is no host's."""
    named = A_HOST.match(host)
    return None if named is None else int(named["release"])

"""The name a release's process runs under: the app, the release and a stamp, short enough for a host name."""

from runtime.enums import Env
from runtime.hosting.service.hostnames import host_of, is_host_of, release_of

SOURCE = "a" * 64


def test_a_host_names_the_app_the_release_and_a_stamp_and_fits_a_host_name() -> None:
    """Another org, env, release or set of secrets is another host; the longest still fits 63."""
    host = host_of("org_1", Env.production, "support", 7, SOURCE, "")
    assert host.startswith("support-r7-")
    assert len(host) == len("support-r7-") + 8
    others = {
        host_of("org_1", Env.production, "support", 7, SOURCE, "CRM_TOKEN@1.5"),
        host_of("org_1", Env.production, "support", 8, SOURCE, ""),
        host_of("org_2", Env.production, "support", 7, SOURCE, ""),
        host_of("org_1", Env.sandbox, "support", 7, SOURCE, ""),
    }
    assert host not in others
    assert len(others) == 4
    assert len(host_of("org_1", Env.production, "x" * 40, 123456, SOURCE, "")) <= 63
    assert (release_of(host), release_of("support-r7")) == (7, None)


def test_a_host_is_the_apps_whatever_its_release_and_never_a_longer_names() -> None:
    """support-rest's host is not support's."""
    assert is_host_of("support", host_of("org_1", Env.production, "support", 3, SOURCE, ""))
    assert not is_host_of("support", host_of("org_1", Env.production, "support-rest", 3, SOURCE, ""))
    assert not is_host_of("support", "support-r3")

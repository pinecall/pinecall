"""What each process of a server is handed and how it is confined: what pinecall.io/security says the suite holds."""

import re
from pathlib import Path

import pytest

from runtime.cli.setup.files import find_shipped

# What a process that decodes a caller's audio and runs the vendors' plugins never holds: a way into
# the database or Redis, the vault's key, the operator's door, the key the gateway signs tokens with.
NEVER_A_WORKERS = frozenset(
    {
        "DATABASE_URL",
        "PINECALL_DB_APP_URL",
        "PINECALL_REDIS_URL",
        "PINECALL_REDIS_PASSWORD",
        "PINECALL_VAULT_KEY",
        "PINECALL_OPS_KEY",
        "PINECALL_TOKEN_KEY",
        "PINECALL_RUNNER_KEY",
        "PINECALL_TURNSTILE_SECRET",
        "PINECALL_SMTP_URL",
    }
)
WORKERS = ("worker-sandbox", "worker-production", "overflow-sandbox", "overflow-production")
RUNTIME = ("gateway", "gateway-b", *WORKERS, "retention")
THIRD_PARTY = ("postgres", "redis", "livekit-server", "sip-server", "postgres-backup")
CHART_ENV = Path(__file__).resolve().parents[4] / "infra" / "charts" / "pinecall" / "templates" / "_env.tpl"


def blocks() -> dict[str, str]:
    """Each top-level anchor and each service of server.yaml, as its own lines."""
    text = find_shipped("server.yaml").read_text(encoding="utf-8")
    # The volumes' names at the end (`redis` among them) are no services.
    text = text.split("\nvolumes:\n", 1)[0]
    found: dict[str, str] = {}
    for part in re.split(r"\n(?=x-[a-z-]+: &|  [a-z][a-z-]*:\n)", text):
        head = part.split(":", 1)[0].strip()
        found[head] = part
    return found


def named_in(block: str) -> set[str]:
    """Every variable a block hands its process or reads its values from."""
    return set(re.findall(r"^\s+([A-Z][A-Z0-9_]+):", block, re.M)) | set(re.findall(r"\$\{([A-Z0-9_]+)", block))


def test_no_process_of_a_server_runs_as_root_keeps_a_capability_or_writes_its_image() -> None:
    """Every process is a user of its own with no capability, no privilege to gain and a root it cannot write."""
    found = blocks()
    confined = found["x-confined"]
    assert "cap_drop: [ALL]" in confined and '"no-new-privileges:true"' in confined
    assert "read_only: true" in confined
    assert "<<: *confined" in found["x-runtime"] and 'user: "10001:10001"' in found["x-runtime"]
    for service in RUNTIME:
        assert "<<: *runtime" in found[service] and "user:" not in found[service], service
    for service in THIRD_PARTY:
        assert "<<: *confined" in found[service], service
        assert re.search(r'user: "(?!0:)\d+:\d+"', found[service]), service
    # Caddy keeps one capability, to take :80 and :443, which its binary holds as a file's.
    caddy = found["caddy"]
    assert 'user: "10001:10001"' in caddy and "cap_drop: [ALL]" in caddy and "read_only: true" in caddy
    assert "cap_add: [NET_BIND_SERVICE]" in caddy


def test_the_one_run_as_root_only_changes_owners_and_has_no_network() -> None:
    """`own` makes the recordings and the certificates the runtime's user's, and can do nothing else."""
    own = blocks()["own"]
    assert 'user: "0:0"' in own and "cap_add: [CHOWN, DAC_READ_SEARCH]" in own and "<<: *confined" in own
    assert "network_mode: none" in own and 'entrypoint: ["find"]' in own


def test_a_worker_is_handed_no_database_no_vault_and_no_operators_key() -> None:
    """A worker and an overflow are given their reads by name, never the env file, and none is a way in."""
    found = blocks()
    reads = named_in(found["x-worker-reads"])
    assert {"LIVEKIT_API_SECRET", "PINECALL_RECORDINGS"} <= reads and reads.isdisjoint(NEVER_A_WORKERS)
    for service in WORKERS:
        block = found[service]
        assert "env_file" not in block and "<<: *worker-reads" in block, service
        assert named_in(block).isdisjoint(NEVER_A_WORKERS), service
        assert "PINECALL_WORKER_KEY" in block, service


def test_a_worker_that_does_not_answer_is_no_worker_up() -> None:
    """Each worker and overflow answers its health on a port of its own: compose waits for it, Docker restarts it."""
    found = blocks()
    assert "start_period:" in found["x-answers-calls"] and "PINECALL_WORKER_HTTP_PORT" in found["x-answers-calls"]
    for service in WORKERS:
        assert "healthcheck: *answers-calls" in found[service], service
    ports = [re.search(r'PINECALL_(?:WORKER|OVERFLOW)_HTTP_PORT: "(\d+)"', found[service]) for service in WORKERS]
    assert len({port.group(1) for port in ports if port}) == len(WORKERS)


def test_the_gateways_reach_postgres_as_the_role_that_changes_no_table() -> None:
    """The env file whole, but the database as the app's role: only setup's migrations sign in as the owner."""
    found = blocks()
    for gateway in ("gateway", "gateway-b"):
        assert "env_file: ./env" in found[gateway]
        assert 'DATABASE_URL: "${PINECALL_DB_APP_URL:?' in found[gateway], gateway


def test_the_night_reads_the_database_the_vault_and_the_recordings_alone() -> None:
    """The retention signs in as the owner (it makes and drops the log's days) and holds no other key."""
    night = blocks()["retention"]
    assert "env_file" not in night
    handed = named_in(night)
    assert {"DATABASE_URL", "PINECALL_VAULT_KEY"} <= handed
    assert handed.isdisjoint(NEVER_A_WORKERS - {"DATABASE_URL", "PINECALL_VAULT_KEY"})


def test_no_config_of_a_server_holds_a_secret_in_a_file_of_its_own() -> None:
    """LiveKit's and SIP's configs are said from the env file's values, and Redis asks a password."""
    found = blocks()
    assert "LIVEKIT_CONFIG: |" in found["livekit-server"] and "volumes" not in found["livekit-server"]
    assert "SIP_CONFIG_BODY: |" in found["sip-server"] and "volumes" not in found["sip-server"]
    for service in ("redis", "livekit-server", "sip-server"):
        assert "${PINECALL_REDIS_PASSWORD:?" in found[service], service


@pytest.mark.skipif(not CHART_ENV.is_file(), reason="the repository's charts, beside the package")
def test_a_clusters_worker_is_handed_none_of_them_either() -> None:
    """The chart's worker and overflow take `pinecall.workerEnv`, which names no way in either."""
    template = CHART_ENV.read_text(encoding="utf-8")
    block = template.split('define "pinecall.workerEnv"', 1)[1].split("{{- end -}}", 1)[0]
    handed = set(re.findall(r"- name: ([A-Z0-9_]+)", block))
    assert "PINECALL_WORKER_KEY" in handed and handed.isdisjoint(NEVER_A_WORKERS)

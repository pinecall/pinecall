"""This machine's containers: a host's lock-down as Docker is told it, its states, and what a stop removes."""

import asyncio
import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from runtime.exceptions import UpstreamError
from runtime.hosts.service.containers import (
    APP,
    HOST_LABEL,
    INSTALL,
    STAGE_LABEL,
    Containers,
    Ran,
    as_cpus,
    container_of,
)
from runtime.hosts.service.place import INSTALL_WITHIN_S, Launch

HOST = "front-r1-0a1b2c3d"
SOURCE = b"the release, packed"
STARTED = "2026-11-23T10:00:00.123456789Z"


@dataclass
class _Docker:
    """Docker as a fake: every command it was given, and an answer for the ones a test names."""

    runtimes: tuple[str, ...] = ("runc", "gvisor")
    has_network: bool = True
    install_exit: int = 0
    # What Docker says of an install of the same name left from before: its state and its exit.
    installed_before: str = ""
    listed: Sequence[Mapping[str, Any]] = ()
    logs: Mapping[str, str] = field(default_factory=dict[str, str])
    commands: list[list[str]] = field(default_factory=list[list[str]])
    given: list[bytes | None] = field(default_factory=list[bytes | None])
    environments: list[Mapping[str, str] | None] = field(default_factory=list[Mapping[str, str] | None])

    async def __call__(
        self, arguments: Sequence[str], given: bytes | None, environment: Mapping[str, str] | None
    ) -> Ran:
        words = list(arguments)
        self.commands.append(words)
        self.given.append(given)
        self.environments.append(environment)
        if words[0] == "info":
            return Ran(0, json.dumps({name: {"path": name} for name in self.runtimes}))
        if words[:2] == ["network", "inspect"]:
            return Ran(0 if self.has_network else 1, "")
        if words[0] == "run" and "-i" in words:
            return Ran(self.install_exit, "")
        if words[0] == "ps":
            names = [each["Name"].lstrip("/") for each in self.listed]
            return Ran(0, "\n".join(names))
        if words[:2] == ["inspect", "--format"]:
            return Ran(0, self.installed_before) if self.installed_before else Ran(1, "", "no such object")
        if words[0] == "inspect":
            return Ran(0, json.dumps(list(self.listed)))
        if words[0] == "logs":
            said = self.logs.get(words[-1])
            return Ran(0, said) if said is not None else Ran(1, "", "no such container")
        return Ran(0, "")

    def ran(self, *start: str) -> list[list[str]]:
        """The commands that began with these words."""
        return [words for words in self.commands if words[: len(start)] == list(start)]


RESOLVERS_FILE = "resolv.conf"


def _containers(docker: _Docker, home: Path | None = None) -> Containers:
    return Containers(
        image="registry/pinecall/app:1",
        runtime="gvisor",
        network="pinecall-apps",
        resolvers=(home or Path(tempfile.mkdtemp())) / RESOLVERS_FILE,
        docker=docker,
    )


def _launch(exits: tuple[float, ...] = ()) -> Launch:
    return Launch(
        env="sandbox",
        app="acme/front",
        host=HOST,
        release=3,
        sha256="",
        source=SOURCE,
        arguments=["start"],
        exits=exits,
    )


def _found(stage: str, status: str, exit_code: int = 0, exits: str = "") -> dict[str, Any]:
    labels = {
        HOST_LABEL: HOST,
        STAGE_LABEL: stage,
        "pinecall.io/world": "sandbox",
        "pinecall.io/app": "acme/front",
        "pinecall.io/release": "3",
        "pinecall.io/exits": exits,
    }
    name = HOST if stage == APP else f"{HOST}-install"
    return {
        "Name": f"/{name}",
        "State": {"Status": status, "ExitCode": exit_code, "StartedAt": STARTED},
        "Config": {"Labels": labels},
    }


async def _started(containers: Containers, environment: Mapping[str, str]) -> None:
    await containers.start(_launch(), environment)
    await asyncio.gather(*(held.task for held in list(containers.installing.values()) if held.task is not None))


def _has(words: Sequence[str], *run: str) -> bool:
    return any(list(words[at : at + len(run)]) == list(run) for at in range(len(words)))


async def test_a_release_is_installed_then_run_under_the_sandbox_with_no_root_and_no_capability() -> None:
    """Both containers of a host are told the sandbox, the user, the read-only root, the ceilings and the network."""
    docker = _Docker()
    await _started(_containers(docker), {"PINECALL_KEY": "k"})
    install = next(words for words in docker.ran("run") if "-i" in words)
    app = next(words for words in docker.ran("run") if "-d" in words)
    for words in (install, app):
        assert _has(words, "--runtime", "gvisor")
        assert _has(words, "--user", "1000:1000")
        assert "--read-only" in words
        assert _has(words, "--cap-drop", "ALL")
        assert _has(words, "--security-opt", "no-new-privileges")
        assert _has(words, "--network", "pinecall-apps")
        assert _has(words, "--pids-limit", "512")
        assert "--privileged" not in words
        assert "--cap-add" not in words
    assert _has(install, "--memory", "1g")
    assert _has(app, "--memory", "256m")
    assert _has(app, "--cpus", "0.5")


async def test_the_release_arrives_on_the_installs_input_and_no_folder_of_the_machine_is_mounted() -> None:
    """The sources are the install's input; a mount is a volume of the host's own, or the runner's file of resolvers."""
    docker = _Docker()
    await _started(_containers(docker), {})
    at = next(index for index, words in enumerate(docker.commands) if words[0] == "run" and "-i" in words)
    assert docker.given[at] == SOURCE
    for words in docker.ran("run"):
        mounted = [words[index + 1] for index, word in enumerate(words) if word == "-v"]
        assert mounted
        assert all(
            mount.startswith(f"{HOST}-") or mount.endswith(f"{RESOLVERS_FILE}:/etc/resolv.conf:ro") for mount in mounted
        )
        assert "/var/run/docker.sock" not in " ".join(words)


async def test_the_app_reads_what_its_install_wrote_and_writes_none_of_it() -> None:
    """The app's two volumes are read-only, and the install's home is not the app's."""
    docker = _Docker()
    await _started(_containers(docker), {})
    app = next(words for words in docker.ran("run") if "-d" in words)
    mounted = [app[index + 1] for index, word in enumerate(app) if word == "-v"]
    assert [mount for mount in mounted if mount.startswith(HOST)] == [
        f"{HOST}-app:/app:ro",
        f"{HOST}-cli:/opt/pinecall:ro",
    ]


async def test_names_are_asked_of_public_resolvers_alone_from_a_file_no_container_writes(tmp_path: Path) -> None:
    """Both containers read the runner's file of resolvers, read-only, and Docker's own resolver is not asked."""
    docker = _Docker()
    await _started(_containers(docker, tmp_path), {})
    assert (tmp_path / RESOLVERS_FILE).read_text() == "nameserver 1.1.1.1\nnameserver 8.8.8.8\n"
    for words in (run for run in docker.ran("run") if "-i" in run or "-d" in run):
        assert _has(words, "-v", f"{tmp_path / RESOLVERS_FILE}:/etc/resolv.conf:ro")
        assert "--dns" not in words


async def test_a_value_of_the_environment_is_never_on_the_command_line() -> None:
    """A variable is named on the command and its value rides the command's own environment."""
    docker = _Docker()
    await _started(
        _containers(docker), {"PINECALL_KEY": "pc_secret_value", "PINECALL_URL": "https://voice.example.com"}
    )
    app_at = next(index for index, words in enumerate(docker.commands) if words[0] == "run" and "-d" in words)
    app = docker.commands[app_at]
    assert _has(app, "-e", "PINECALL_KEY")
    assert "pc_secret_value" not in " ".join(app)
    assert docker.environments[app_at] == {
        "PINECALL_KEY": "pc_secret_value",
        "PINECALL_URL": "https://voice.example.com",
    }


async def test_no_app_starts_on_a_machine_whose_docker_lacks_the_sandbox() -> None:
    """A Docker with no such runtime starts nothing: an app never runs unfenced."""
    docker = _Docker(runtimes=("runc",))
    with pytest.raises(UpstreamError, match="no runtime named gvisor"):
        await _containers(docker).start(_launch(), {})
    assert not docker.ran("run")
    assert not docker.ran("volume")


async def test_no_app_starts_on_a_machine_with_no_network_for_the_apps() -> None:
    """A Docker with no such network starts nothing."""
    docker = _Docker(has_network=False)
    with pytest.raises(UpstreamError, match="no network named pinecall-apps"):
        await _containers(docker).start(_launch(), {})
    assert not docker.ran("run")


async def test_a_name_that_is_no_variable_is_refused_before_anything_is_made() -> None:
    """An environment name Docker would read as an option is refused."""
    docker = _Docker()
    with pytest.raises(UpstreamError, match="not an environment variable"):
        await _containers(docker).start(_launch(), {"--privileged": "1"})
    assert not docker.ran("run")


async def test_an_install_that_fails_never_runs_the_app() -> None:
    """The app's container is made only after its install ended well."""
    docker = _Docker(install_exit=1)
    await _started(_containers(docker), {})
    assert not [words for words in docker.ran("run") if "-d" in words]


async def test_a_stop_removes_the_hosts_containers_and_its_volumes() -> None:
    """The app is told to stop with its grace, then both containers and the three volumes go."""
    docker = _Docker()
    await _containers(docker).stop(HOST, 7)
    assert docker.ran("stop") == [["stop", "-t", "7", HOST]]
    assert docker.ran("rm") == [["rm", "-f", HOST, f"{HOST}-install"]]
    assert docker.ran("volume", "rm") == [["volume", "rm", "-f", f"{HOST}-app", f"{HOST}-cli", f"{HOST}-home"]]


async def test_the_logs_are_the_apps_and_its_installs_when_it_never_ran() -> None:
    """What a host printed is its app's output, or its install's when there is no app."""
    ran = _containers(_Docker(logs={HOST: "serving\n", f"{HOST}-install": "installed\n"}))
    never_ran = _containers(_Docker(logs={f"{HOST}-install": "npm said no\n"}))
    assert await ran.read_logs(HOST, 20) == "serving\n"
    assert await never_ran.read_logs(HOST, 20) == "npm said no\n"
    assert await _containers(_Docker()).read_logs(HOST, 20) == ""


async def test_a_listing_is_one_host_for_its_two_containers() -> None:
    """The env's containers are found by their label and read as one host each."""
    docker = _Docker(
        listed=[_found(INSTALL, "exited", exits="1700000000.5"), _found(APP, "running", exits="1700000000.5")]
    )
    listed = await _containers(docker).list_running("sandbox")
    assert docker.ran("ps") == [["ps", "-a", "--filter", "label=pinecall.io/world=sandbox", "--format", "{{.Names}}"]]
    assert [(each.name, each.app, each.release, each.state) for each in listed] == [(HOST, "acme/front", 3, "running")]
    assert listed[0].exits == (1700000000.5,)
    assert await _containers(_Docker()).list_running("sandbox") == []


@pytest.mark.parametrize(
    ("found", "installing", "state"),
    [
        ([_found(INSTALL, "running")], True, "pending"),
        ([_found(INSTALL, "exited", 0)], True, "pending"),
        ([_found(INSTALL, "exited", 1)], True, "exited"),
        ([_found(INSTALL, "exited", 0)], False, "exited"),
        ([_found(INSTALL, "exited", 0), _found(APP, "created")], False, "pending"),
        ([_found(INSTALL, "exited", 0), _found(APP, "running")], False, "running"),
        ([_found(INSTALL, "exited", 0), _found(APP, "exited", 2)], False, "exited"),
    ],
)
def test_a_host_is_pending_while_it_installs_running_once_its_app_is_and_exited_when_either_ended_badly(
    found: list[dict[str, Any]], installing: bool, state: str
) -> None:
    """An install that ended well with no runner holding it is a host whose runner died: it exited."""
    assert container_of(HOST, found, installing=installing).state == state


def test_a_host_that_still_installs_is_given_the_installs_time_before_it_is_timed() -> None:
    """Its start is its install's start plus the install's clock, as a pod not yet running is read."""
    installing = container_of(HOST, [_found(INSTALL, "running")], installing=True)
    running = container_of(HOST, [_found(INSTALL, "exited"), _found(APP, "running")], installing=False)
    assert installing.started_at - running.started_at == pytest.approx(INSTALL_WITHIN_S)


def test_a_pods_share_of_a_core_is_dockers() -> None:
    """`250m` is a quarter of a core; unset, the half core an app may take."""
    assert as_cpus("250m") == "0.25"
    assert as_cpus(None) == "0.5"


async def test_a_host_just_asked_for_is_listed_as_installing_before_docker_has_its_container() -> None:
    """Between the asking and its first container a host is pending, so no beat starts it a second time."""
    docker = _Docker()
    containers = _containers(docker)
    await containers.start(_launch(exits=(1700000000.5,)), {})
    listed = await containers.list_running("sandbox")
    assert [(each.name, each.app, each.release, each.state, each.exits) for each in listed] == [
        (HOST, "acme/front", 3, "pending", (1700000000.5,))
    ]
    assert await containers.list_running("production") == []
    await containers.close()


async def test_a_release_already_installed_is_run_as_it_is_and_never_installed_twice() -> None:
    """An install of the host's name that ended well is kept with its volumes: only the app's container is made."""
    docker = _Docker(installed_before="exited 0\n")
    await _started(_containers(docker), {"PINECALL_KEY": "k"})
    assert not [words for words in docker.ran("run") if "-i" in words]
    assert not docker.ran("volume")
    assert docker.ran("rm") == [["rm", "-f", HOST]]
    assert len([words for words in docker.ran("run") if "-d" in words]) == 1


async def test_an_install_that_ended_badly_is_made_again_from_nothing() -> None:
    """What a failed install left goes, volumes and all, before the release is installed again."""
    docker = _Docker(installed_before="exited 1\n")
    await _started(_containers(docker), {})
    assert docker.ran("rm") == [["rm", "-f", HOST, f"{HOST}-install"]]
    assert len([words for words in docker.ran("run") if "-i" in words]) == 1

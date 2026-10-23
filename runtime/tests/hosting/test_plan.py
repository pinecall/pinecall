"""What the runner does with what it sees: numbers in, steps out; the cluster's own hand is never a crash."""

from pinecall_runtime.hosting.schemas import WantedApp
from pinecall_runtime.hosting.service.cluster import Container
from pinecall_runtime.hosting.service.plan import (
    CRASH_WINDOW_S,
    EXITED,
    KEEPS_EXITING,
    MOST_CRASHES,
    NEVER_REGISTERED,
    Failed,
    Revive,
    Start,
    Stop,
    planned,
)

NOW = 10_000.0
HOST = "support-r3-aaaaaaaa"


def an_app(*, live_host: str | None = HOST, failed: bool = False, registered: bool = True) -> WantedApp:
    """The app the gateway wants running: release 3, served by HOST unless said otherwise."""
    return WantedApp(
        org="org_1",
        name="support",
        release=3,
        sha256="f" * 64,
        host=HOST,
        registered=registered,
        failed=failed,
        logs_wanted=False,
        live_host=live_host,
    )


def a_pod(state: str, *, deleting: bool = False, evicted: bool = False, name: str = HOST) -> Container:
    """The app's pod as the listing shows it."""
    return Container(
        name=name, app="org_1/support", release=3, state=state, started_at=NOW - 600, deleting=deleting, evicted=evicted
    )


def test_a_process_that_exited_on_its_own_is_run_again_and_counted() -> None:
    (step,) = planned([an_app()], [a_pod("Failed")], {}, NOW)["org_1/support"]
    assert step == Revive(an_app(), a_pod("Failed"), crashed=True)


def test_a_pod_the_cluster_is_deleting_is_waited_out_and_started_again_once_gone() -> None:
    assert planned([an_app()], [a_pod("Succeeded", deleting=True)], {}, NOW) == {}
    (step,) = planned([an_app()], [], {}, NOW)["org_1/support"]
    assert step == Start(an_app())


def test_a_pod_the_cluster_evicted_is_run_again_at_once_and_never_counted() -> None:
    too_many = {HOST: [NOW - 10.0 * n for n in range(MOST_CRASHES)]}
    (step,) = planned([an_app()], [a_pod("Failed", evicted=True)], too_many, NOW)["org_1/support"]
    assert step == Revive(an_app(), a_pod("Failed", evicted=True), crashed=False)


def test_the_sixth_exit_of_the_processs_own_in_the_window_gives_up_and_says_so_whole() -> None:
    five = {HOST: [NOW - 10.0 * n for n in range(MOST_CRASHES)]}
    steps = planned([an_app()], [a_pod("Failed")], five, NOW)["org_1/support"]
    assert steps == [Failed(an_app(), KEEPS_EXITING, a_pod("Failed")), Stop(a_pod("Failed"))]
    first_line = KEEPS_EXITING.split("\n")[0]
    assert first_line == "the process exited again after 5 restarts in 10 minutes and is not run again; its last lines:"
    old = {HOST: [NOW - CRASH_WINDOW_S - 1.0 - n for n in range(MOST_CRASHES)]}
    (step,) = planned([an_app()], [a_pod("Failed")], old, NOW)["org_1/support"]
    assert isinstance(step, Revive)


def test_a_host_that_never_served_and_exited_is_failed_at_once() -> None:
    before = a_pod("Running", name="support-r2-bbbbbbbb")
    app = an_app(live_host=before.name, registered=False)
    steps = planned([app], [a_pod("Failed"), before], {}, NOW)["org_1/support"]
    assert steps == [Failed(app, EXITED, a_pod("Failed")), Stop(a_pod("Failed"))]
    for text in (EXITED, NEVER_REGISTERED, KEEPS_EXITING):
        assert not text.split("\n")[0].endswith(":\n") and text.split("\n")[0].endswith("its last lines:")


def test_a_failed_host_is_stopped_and_nothing_of_the_app_is_kept() -> None:
    steps = planned([an_app(failed=True)], [a_pod("Running")], {}, NOW)["org_1/support"]
    assert steps == [Stop(a_pod("Running"))]

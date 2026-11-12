"""The runner process: an env's hosted apps kept running, on the hosting cluster or as this machine's processes."""

import socket

from runtime.config import Settings
from runtime.exceptions import ConfigurationError
from runtime.hosts import service as hosts
from runtime.hosts import tasks as hosts_tasks
from runtime.kit.loops import Loops
from runtime.kit.signals import stop_on_a_signal

NO_KEY = "PINECALL_RUNNER_KEY: a runner signs in to its gateway with its env's runner key"


# The first beat goes out as the loop starts. On the way out the steps under way are cut short and
# the place decides what becomes of its hosts: a cluster's pods go on, this machine's processes stop.
async def run_runner(settings: Settings) -> int:
    """Keep the env's hosted apps running until told to stop; the exit it leaves with."""
    if settings.runner_key is None:
        raise ConfigurationError(NO_KEY)
    stopping = stop_on_a_signal()
    gateway = hosts.open_gateway(settings.gateway_url, settings.runner_key.get_secret_value())
    runner = hosts.Runner(
        hosts=await _open_place(settings),
        gateway=gateway,
        address=settings.gateway_url,
        name=socket.gethostname().split(".")[0],
    )
    loops = Loops()
    loops.start(hosts_tasks.beat.bind(runner))
    await stopping.wait()
    await loops.stop()
    await runner.close()
    await gateway.aclose()
    return 0


# A pod fetches its release from the runner by digest, so the cluster's place serves the sources.
async def _open_place(settings: Settings) -> hosts.Hosts:
    if settings.runner_engine == "processes":
        return hosts.Processes(settings.runner_home)
    engine = hosts.Engine(
        image=settings.runner_image,
        runtime_class=settings.runner_runtime_class,
        namespace=settings.runner_namespace,
        sources_url=settings.runner_sources_url,
    )
    cluster = hosts.in_cluster(engine)
    await cluster.serve_sources(settings.runner_listen, settings.runner_port)
    return cluster

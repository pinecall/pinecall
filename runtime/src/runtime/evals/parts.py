"""The harness's parts: one of each thing a test call reaches, built once and handed to evals' use cases."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runtime.alerts import service as alerts
from runtime.calls.log import Feeds, Logs, Store
from runtime.config import Settings
from runtime.evals.service.briefs import Describers
from runtime.evals.tasks import Runner, Simulations
from runtime.fleet import service as fleet
from runtime.judging import service as judging
from runtime.kit.crypto import Vault
from runtime.live import service as live
from runtime.livekit import Servers
from runtime.platform import service as platform


# A test call is placed as a real one is, by the gateway playing the caller: it reaches the logs, the
# fleet, the apps that hold agents, the vault's keys and the runs and simulations this gateway keeps.
# With sixteen parameters a signature says nothing, so they travel as one value, as the live side's do
# (`live.parts.LiveParts`), and under the same rule: it never leaves this domain, and a use case that
# needs two or three of these takes them by name.
@dataclass(frozen=True, slots=True)
class Harness:
    """What places and plays a test call on this gateway: the process's connections, the logs, evals' own objects."""

    settings: Settings
    vault: Vault
    servers: Servers
    sessions: async_sessionmaker[AsyncSession]
    store: Store
    logs: Logs
    feeds: Feeds
    prompts: judging.PromptTexts
    # The apps that hold agents here, and what signs a caller's way into a room: the live side's own.
    apps: live.ServingApps
    signer: live.Signer
    offering: fleet.Offering
    roster: fleet.Roster
    alerting: alerts.Alerting
    describers: Describers
    runner: Runner
    simulations: Simulations
    # A caller's line is a model call: an org asks for so many a minute and no more.
    caller_lines: platform.AttemptThrottle
